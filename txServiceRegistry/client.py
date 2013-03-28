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
    def __init__(self, finished, heartbeater=None):
        """
        @param finished: Deferred to callback with result in connectionLost
        @type finished: L{Deferred}
        @param heartbeater: Optional HeartBeater object created when a
        session is created.
        @type heartbeater: L{HeartBeater}
        """
        self.finished = finished
        self.remaining = StringIO()
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

        try:
            result = json.load(self.remaining)
        except Exception, e:
            self.finished.errback(e)
            return

        returnValue = result
        if self.heartbeater:
            self.heartbeater.nextToken = result['token']
            returnValue = (result, self.heartbeater)

        self.finished.callback(returnValue)


class BaseClient(object):
    """
    A base client for SessionsClient, EventsClient, ServicesClient,
    ConfigurationClient, and AccountClient to inherit from so they can call
    BaseClient.request()
    """
    def __init__(self, agent, baseUrl):
        self.agent = agent
        self.baseUrl = baseUrl

    def _get_options_object(self, marker=None, limit=None):
        options = {}

        if marker:
            options['marker'] = marker

        if limit:
            options['limit'] = limit

        return options

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
            # If response has no body, callback with True
            if response.code == httplib.NO_CONTENT:
                finished.callback(True)

                return finished

            response.deliverBody(ResponseReceiver(finished,
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


class EventsClient(BaseClient):
    def __init__(self, agent, baseUrl):
        super(EventsClient, self).__init__(agent, baseUrl)
        self.eventsPath = '/events'

    def list(self, marker=None, limit=None):
        options = self._get_options_object(marker, limit)

        return self.request('GET', self.eventsPath, options=options)


class ServicesClient(BaseClient):
    def __init__(self, agent, baseUrl):
        super(ServicesClient, self).__init__(agent, baseUrl)
        self.servicesPath = '/services'

    def list(self, marker=None, limit=None):
        options = self._get_options_object(marker, limit)

        return self.request('GET', self.servicesPath, options=options)

    def listForTag(self, tag, marker=None, limit=None):
        options = self._get_options_object(marker, limit)
        options['tag'] = tag

        return self.request('GET', self.servicesPath, options=options)

    def get(self, serviceId):
        path = '%s/%s' % (self.servicesPath, serviceId)

        return self.request('GET', path)

    def create(self, serviceId, heartbeatTimeout, payload=None):
        payload = deepcopy(payload) if payload else {}
        payload['id'] = serviceId
        payload['heartbeat_timeout'] = heartbeatTimeout
        heartbeater = HeartBeater(self.agent,
                                  self.baseUrl,
                                  None,
                                  heartbeatTimeout)

        return self.request('POST', self.servicesPath, payload=payload,
                            heartbeater=heartbeater)

    def heartbeat(self, serviceId, token):
        path = '%s/%s/heartbeat' % (self.servicesPath, serviceId)
        payload = {'token': token}

        return self.request('POST', path, payload=payload)

    def update(self, serviceId, payload):
        path = '%s/%s' % (self.servicesPath, serviceId)

        return self.request('PUT', path, payload=payload)

    def remove(self, serviceId):
        path = '%s/%s' % (self.servicesPath, serviceId)

        return self.request('DELETE', path)

    def register(self, serviceId, heartbeatTimeout, payload=None,
                 retryDelay=2):
        retryCount = MAX_HEARTBEAT_TIMEOUT / retryDelay
        success = False
        retryCounter = 0
        registerResult = Deferred()
        lastErr = None

        def doRegister(serviceId, heartbeatTimeout, retryCounter,
                       success, lastErr, result=None):
            if success and (retryCounter < retryCount):
                registerResult.callback(result)
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
                        reactor.callLater(retryDelay, doRegister,
                                          serviceId, heartbeatTimeout,
                                          retryCounter, success,
                                          lastErr)

                        return registerResult
                    else:
                        registerResult.errback(lastErr)

                        return registerResult
                else:
                    return doRegister(serviceId, heartbeatTimeout,
                                      retryCounter, True, None, result)

            d = self.create(serviceId, heartbeatTimeout, payload)
            d.addCallback(cbCreate, retryCounter, success)

            return d

        return doRegister(serviceId, heartbeatTimeout, retryCounter, success,
                          lastErr)


class ConfigurationClient(BaseClient):
    def __init__(self, agent, baseUrl):
        super(ConfigurationClient, self).__init__(agent, baseUrl)
        self.configurationPath = '/configuration'

    def list(self, marker=None, limit=None):
        options = self._get_options_object(marker, limit)

        return self.request('GET', self.configurationPath, options=options)

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
        self.events = EventsClient(self.agent, self.baseUrl)
        self.services = ServicesClient(self.agent, self.baseUrl)
        self.configuration = ConfigurationClient(self.agent, self.baseUrl)
        self.account = AccountClient(self.agent, self.baseUrl)
