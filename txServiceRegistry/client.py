# Copyright 2012 Rackspace Hosting, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from cStringIO import StringIO
import httplib
try:
    import simplejson as json
except:
    import json
from copy import deepcopy
import random

from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.internet.protocol import Protocol
from twisted.python import log
from twisted.web.client import Agent, HTTPConnectionPool
from urllib import urlencode

from txKeystone import KeystoneAgent

from utils import StringProducer

US_AUTH_URL = 'https://identity.api.rackspacecloud.com/v2.0/tokens'
UK_AUTH_URL = 'https://lon.identity.api.rackspacecloud.com/v2.0/tokens'
DEFAULT_AUTH_URLS = {'us': US_AUTH_URL,
                     'uk': UK_AUTH_URL}
DEFAULT_API_URL = 'https://dfw.registry.api.rackspacecloud.com/v1.0/'
MAX_HEARTBEAT_TIMEOUT = 30
MAX_401_RETRIES = 1


class ResponseReceiver(Protocol):
    """
    Receives the response, and the response body is delivered to dataReceived
    as it arrives.
    When the body has been completely delivered, connectionLost is called.
    """
    def __init__(self, finished, idFromUrl=None, heartbeater=None):
        """
        @param finished: Deferred to callback with result in connectionLost
        @type finished: L{Deferred}
        @param idFromUrl: Optional session or service ID that was parsed out
        of the location header.
        @type idFromUrl: C{str}
        @param heartbeater: Optional HeartBeater object created when a
        session is created.
        @type heartbeater: L{HeartBeater}
        """
        self.finished = finished
        self.remaining = StringIO()
        self.idFromUrl = idFromUrl
        self.heartbeater = heartbeater

    def dataReceived(self, receivedBytes):
        """
        Writes received response body to self.remaining as it arrives.
        @param receivedBytes: Response body bytes to be written
        to self.remaining
        @type receivedBytes: C{str}
        """
        self.remaining.write(receivedBytes)

    def connectionLost(self, reason):
        """
        Called when the response body has been completely delivered.
        @param reason: Either a twisted.web.client.ResponseDone exception or
        a twisted.web.http.PotentialDataLoss exception.
        """
        self.remaining.reset()
        # When creating a session, the token is returned in the body, and the
        # session ID is in the location header URL. When creating a service,
        # the body is empty, and the service ID is in the location header URL.
        if self.idFromUrl:
            result = None
            if self.remaining.getvalue():
                result = json.load(self.remaining)

            returnTuple = (result, self.idFromUrl)
            if self.heartbeater:
                self.heartbeater.nextToken = result['token']
                returnTuple = returnTuple + (self.heartbeater,)

            # Return just service ID if result is None
            if result is None:
                self.finished.callback(self.idFromUrl)
            else:
                self.finished.callback(returnTuple)

            return

        result = json.load(self.remaining)
        self.finished.callback(result)


class BaseClient(object):
    """
    A base client for SessionsClient, EventsClient, ServicesClient,
    ConfigurationClient, and AccountClient to inherit from so they can call
    BaseClient.request()
    """
    def __init__(self, agent, baseUrl):
        self.agent = agent
        self.baseUrl = baseUrl

    def getIdFromUrl(self, url):
        return url.split('/')[-1]

    def cbRequest(self,
                  response,
                  method,
                  path,
                  options,
                  payload,
                  heartbeater=None,
                  retry_count=0):
        if retry_count < MAX_401_RETRIES:
            retry_count += 1

            if response.code == httplib.UNAUTHORIZED:
                return self.request(method,
                                    path,
                                    options,
                                    payload,
                                    heartbeater,
                                    retry_count)
            finished = Deferred()
            idFromUrl = None
            # If response has no body, callback with True
            if response.code == httplib.NO_CONTENT:
                finished.callback(True)

                return finished

            # If response code is 201, extract service or session id
            # from the location
            if response.code == httplib.CREATED:
                locationHeader = response.headers.getRawHeaders('location')[0]
                idFromUrl = self.getIdFromUrl(locationHeader)
                if 'sessions' in locationHeader:
                    heartbeater.sessionId = idFromUrl

            response.deliverBody(ResponseReceiver(finished,
                                                  idFromUrl,
                                                  heartbeater))

            return finished
        else:
            raise APIError('API returned 401')

    def request(self,
                method,
                path,
                options=None,
                payload=None,
                heartbeater=None,
                retry_count=0):
        """
        Make a request to the Service Registry API.
        @param method: HTTP method ('POST', 'GET', etc.).
        @type method: C{str}
        @param path: Path to be appended to base URL ('/sessions', etc.).
        @type path: C{str}
        @param options: Options to be encoded as query parameters in the URL.
        @type options: C{dict}
        @param payload: Optional body
        @type payload: C{dict}
        @param heartbeater: Optional heartbeater passed in when
        creating a session.
        @type heartbeater: L{HeartBeater}
        """
        def _request(authHeaders, options, payload, heartbeater, retry_count):
            tenantId = authHeaders['X-Tenant-Id']
            requestUrl = self.baseUrl + tenantId + path
            if options:
                requestUrl += '?' + urlencode(options)
            payload = StringProducer(json.dumps(payload)) if payload else None

            d = self.agent.request(method=method,
                                   uri=requestUrl,
                                   headers=None,
                                   bodyProducer=payload)
            d.addCallback(self.cbRequest,
                          method,
                          path,
                          options,
                          payload,
                          heartbeater,
                          retry_count)

            return d

        d = self.agent.getAuthHeaders()
        d.addCallback(_request, options, payload, heartbeater, retry_count)

        return d


class SessionsClient(BaseClient):
    def __init__(self, agent, baseUrl):
        super(SessionsClient, self).__init__(agent, baseUrl)
        self.agent = agent
        self.baseUrl = baseUrl
        self.sessionsPath = '/sessions'

    def list(self):
        path = self.sessionsPath

        return self.request('GET', path)

    def get(self, sessionId):
        path = '%s/%s' % (self.sessionsPath, sessionId)

        return self.request('GET', path)

    def create(self, heartbeatTimeout, payload=None):
        path = self.sessionsPath
        payload = deepcopy(payload) if payload else {}
        payload['heartbeat_timeout'] = heartbeatTimeout
        heartbeater = HeartBeater(self.agent,
                                  self.baseUrl,
                                  None,
                                  heartbeatTimeout)

        return self.request('POST',
                            path,
                            payload=payload,
                            heartbeater=heartbeater)

    def heartbeat(self, sessionId, token):
        path = '%s/%s/heartbeat' % (self.sessionsPath, sessionId)
        payload = {'token': token}

        return self.request('POST', path, payload=payload)

    def update(self, sessionId, payload):
        path = '%s/%s' % (self.sessionsPath, sessionId)

        return self.request('PUT', path, payload=payload)


class EventsClient(BaseClient):
    def __init__(self, agent, baseUrl):
        super(EventsClient, self).__init__(agent, baseUrl)
        self.eventsPath = '/events'

    def list(self, marker=None):
        options = None
        if marker:
            options = {'marker': marker}

        return self.request('GET', self.eventsPath, options=options)


class ServicesClient(BaseClient):
    def __init__(self, agent, baseUrl):
        super(ServicesClient, self).__init__(agent, baseUrl)
        self.servicesPath = '/services'

    def list(self):
        return self.request('GET', self.servicesPath)

    def listForTag(self, tag):
        options = {'tag': tag}

        return self.request('GET', self.servicesPath, options=options)

    def get(self, serviceId):
        path = '%s/%s' % (self.servicesPath, serviceId)

        return self.request('GET', path)

    def create(self, sessionId, serviceId, payload=None):
        payload = deepcopy(payload) if payload else {}
        payload['session_id'] = sessionId
        payload['id'] = serviceId

        return self.request('POST', self.servicesPath, payload=payload)

    def update(self, serviceId, payload):
        path = '%s/%s' % (self.servicesPath, serviceId)

        return self.request('PUT', path, payload=payload)

    def remove(self, serviceId):
        path = '%s/%s' % (self.servicesPath, serviceId)

        return self.request('DELETE', path)

    def register(self, sessionId, serviceId, payload=None, retryDelay=2):
        retryCount = MAX_HEARTBEAT_TIMEOUT / retryDelay
        success = False
        retryCounter = 0
        registerResult = Deferred()
        lastErr = None

        def doRegister(sessionId, serviceId, retryCounter, success, lastErr):
            if success and (retryCounter < retryCount):
                registerResult.callback(serviceId)

                return registerResult

            elif (not success) and (retryCounter == retryCount):
                registerResult.errback(lastErr)

                return registerResult

            def cbCreate(result, retryCounter, success):
                # Create service returns a string service ID when it has
                # succeeded, so if the result is a dict, it should be a
                # parsed response body containing an error
                if isinstance(result, dict):
                    lastErr = result
                    if result['type'] == 'serviceWithThisIdExists':
                        retryCounter += 1
                        reactor.callLater(retryDelay, doRegister, sessionId,
                                          serviceId, retryCounter, success,
                                          lastErr)

                        return registerResult
                    else:
                        registerResult.errback(lastErr)

                        return registerResult
                else:
                    return doRegister(sessionId, serviceId, retryCounter,
                                      True, None)

            d = self.create(sessionId, serviceId, payload)
            d.addCallback(cbCreate, retryCounter, success)

            return d

        return doRegister(sessionId, serviceId, retryCounter, success, lastErr)


class ConfigurationClient(BaseClient):
    def __init__(self, agent, baseUrl):
        super(ConfigurationClient, self).__init__(agent, baseUrl)
        self.configurationPath = '/configuration'

    def list(self):
        return self.request('GET', self.configurationPath)

    def get(self, configurationId):
        path = '%s/%s' % (self.configurationPath, configurationId)

        return self.request('GET', path)

    def set(self, configurationId, value):
        path = '%s/%s' % (self.configurationPath, configurationId)
        payload = {'value': value}

        return self.request('PUT', path, payload=payload)

    def remove(self, configurationId):
        path = '%s/%s' % (self.configurationPath, configurationId)

        return self.request('DELETE', path)


class AccountClient(BaseClient):
    def __init__(self, agent, baseUrl):
        super(AccountClient, self).__init__(agent, baseUrl)
        self.limitsPath = '/limits'

    def getLimits(self):
        return self.request('GET', self.limitsPath)


class HeartBeater(BaseClient):
    def __init__(self, agent, baseUrl, sessionId, heartbeatTimeout):
        """
        HeartBeater will start heartbeating a session once start() is called,
        and stop heartbeating the session when stop() is called.

        @param agent: An instance of txKeystoneAgent.KeystoneAgent
        @type agent: L{KeystoneAgent}
        @param baseUrl:  The base Service Registry URL.
        @type baseUrl: C{str}
        @param sessionId: The ID of the session to heartbeat.
        @type sessionId: C{str}
        @param heartbeatTimeout: The amount of time after which a session will
        time out if a heartbeat is not received.
        @type heartbeatTimeout: C{int}
        """
        super(HeartBeater, self).__init__(agent, baseUrl)
        self.sessionId = sessionId
        self.heartbeatTimeout = heartbeatTimeout
        self.heartbeatInterval = self._calculateInterval(heartbeatTimeout)
        self.nextToken = None
        self._stopped = False

    def _calculateInterval(self, heartbeatTimeout):
        if heartbeatTimeout < 15:
            return heartbeatTimeout * 0.6
        else:
            return heartbeatTimeout * 0.8

    def _startHeartbeating(self):
        path = '/sessions/%s/heartbeat' % self.sessionId
        payload = {'token': self.nextToken}

        if self._stopped:
            return

        interval = self.heartbeatInterval

        if interval > 5:
            interval = interval + random.randrange(-3, 1)

        def cbRequest(result):
            self.nextToken = result['token']

        d = self.request('POST', path, payload=payload)
        d.addCallback(cbRequest)
        self._timeoutId = reactor.callLater(interval, self._startHeartbeating)

    def start(self):
        """
        Start heartbeating the session. Will continue to heartbeat
        until stop() is called.
        """
        return self._startHeartbeating()

    def stop(self):
        """
        Stop heartbeating the session.
        """
        self._stopped = True
        self._timeoutId.cancel()


class APIError(Exception):
    pass


class Client(object):
    """
    The main client to be instantiated by the user.
    """
    def __init__(self, username, apiKey, region='us', baseUrl=DEFAULT_API_URL,
                 agent=None):
        """
        @param username: Rackspace username.
        @type username: C{str}
        @param apiKey: Rackspace API key.
        @type apiKey: C{str}
        @param region: Rackspace region.
        @type region: C{str}
        @param baseUrl: The base Service Registry URL.
        @type baseUrl: C{str}
        @param agent: twisted.web.client.Agent
        @type agent: L{Agent}
        """
        pool = HTTPConnectionPool(reactor)
        agent = agent or Agent(reactor, pool=pool)
        authUrl = DEFAULT_AUTH_URLS.get(region, 'us')

        if not authUrl.endswith('/'):
            authUrl += '/'

        self.agent = KeystoneAgent(agent, authUrl, (username, apiKey))
        self.baseUrl = baseUrl
        self.sessions = SessionsClient(self.agent, self.baseUrl)
        self.events = EventsClient(self.agent, self.baseUrl)
        self.services = ServicesClient(self.agent, self.baseUrl)
        self.configuration = ConfigurationClient(self.agent, self.baseUrl)
        self.account = AccountClient(self.agent, self.baseUrl)
