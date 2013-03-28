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

import mock

from twisted.internet import reactor
from twisted.internet.defer import succeed
from twisted.trial.unittest import TestCase
from twisted.web.client import Agent

from txServiceRegistry.client import Client, HeartBeater

TOKENS = ['6bc8d050-f86a-11e1-a89e-ca2ffe480b20']
EXPECTED_METADATA = \
    {'region': 'dfw',
     'port': '3306',
     'ip': '127.0.0.1',
     'version': '5.5.24-0ubuntu0.12.04.1 (Ubuntu)'}


class ServiceRegistryClientTests(TestCase):
    def setUp(self):
        self.agent = Agent(reactor)
        self.client = Client('user',
                             'api_key',
                             'us',
                             'http://127.0.0.1:8881/',
                             self.agent)
        self.client.agent._getAuthHeaders = \
            lambda: succeed({'X-Auth-Token': 'authToken',
                             'X-Tenant-Id': 'tenantId'})

    def test_getLimits(self):
        expected = \
            {'rate':
                {'/.*': {'window': '24.0 hours', 'used': 0, 'limit': 500000}},
             'resource': {}}

        def limits_assert(result):
            self.assertEqual(result, expected)

        d = self.client.account.getLimits()
        d.addCallback(limits_assert)

        return d

    def test_create_service(self):
        def service_assert(result):
            response_body = {'token': TOKENS[0]}
            self.assertEqual(result[0], response_body)
            self.assertTrue(isinstance(result[1], HeartBeater))
            self.assertEqual(result[1].heartbeatInterval, 12.0)
            self.assertEqual(result[1].nextToken, TOKENS[0])

        d = self.client.services.create('dfw1-db1', 15)
        d.addCallback(service_assert)

        return d

    def test_register_service(self):
        def service_assert(result):
            response_body = {'token': TOKENS[0]}
            self.assertEqual(result[0], response_body)
            self.assertTrue(isinstance(result[1], HeartBeater))
            self.assertEqual(result[1].heartbeatInterval, 12.0)
            self.assertEqual(result[1].nextToken, TOKENS[0])

        d = self.client.services.register('dfw1-db1', 15)
        d.addCallback(service_assert)

        return d

    def test_heartbeat_service(self):
        def heartbeat_assert(result):
            heartbeat_response = {'token': TOKENS[0]}
            self.assertEqual(result, heartbeat_response)

        d = self.client.services.heartbeat('dfw1-db1', 'someToken')
        d.addCallback(heartbeat_assert)

        return d

    def test_get_service(self):
        def service_assert(result):
            self.assertEqual(result['id'], 'dfw1-db1')
            self.assertEqual(result['tags'], ['db', 'mysql'])
            self.assertEqual(result['metadata'], EXPECTED_METADATA)
            self.assertEqual(result['heartbeat_timeout'], 30)
            self.assertTrue('last_seen' in result)

        d = self.client.services.get('dfw1-db1')
        d.addCallback(service_assert)

        return d

    def test_list_services(self):
        def services_assert(result):
            self.assertEqual(result['values'][0]['id'], 'dfw1-api')
            self.assertTrue('tags' in result['values'][0])
            self.assertTrue('metadata' in result['values'][0])
            self.assertEqual(result['values'][1]['id'], 'dfw1-db1')
            self.assertEqual(result['values'][1]['tags'],
                             ['db', 'mysql'])
            self.assertEqual(result['values'][1]['metadata'],
                             EXPECTED_METADATA)
            self.assertTrue('metadata' in result)

        d = self.client.services.list()
        d.addCallback(services_assert)

        return d

    def test_listForTag(self):
        def services_for_tag_assert(result):
            self.assertEqual(result['values'][0]['id'], 'dfw1-db1')
            self.assertEqual(result['values'][0]['tags'],
                             ['db', 'mysql'])
            self.assertEqual(result['values'][0]['metadata'],
                             EXPECTED_METADATA)
            self.assertTrue('metadata' in result)

        d = self.client.services.listForTag('db')
        d.addCallback(services_for_tag_assert)

        return d

    def test_list_configuration(self):
        def configuration_assert(result):
            self.assertEqual(result['values'][0]['id'], 'configId')
            self.assertEqual(result['values'][0]['value'], 'test value 123456')
            self.assertTrue('metadata' in result)

        d = self.client.configuration.list()
        d.addCallback(configuration_assert)

        return d

    def test_get_configuration(self):
        def configuration_assert(result):
            self.assertEqual(result['id'], 'configId')
            self.assertEqual(result['value'], 'test value 123456')

        d = self.client.configuration.get('configId')
        d.addCallback(configuration_assert)

        return d

    @mock.patch('txServiceRegistry.client.BaseClient.request')
    def _marker_assertion(self, path, request):
        client = getattr(self.client, path.strip('/'))
        client.list(marker='someMarker')
        request.assert_called_with('GET', path,
                                   options={'marker': 'someMarker'})

    @mock.patch('txServiceRegistry.client.BaseClient.request')
    def _limit_assertion(self, path, request):
        client = getattr(self.client, path.strip('/'))
        client.list(limit=3)
        request.assert_called_with('GET', path, options={'limit': 3})

    @mock.patch('txServiceRegistry.client.BaseClient.request')
    def _marker_and_limit_assertion(self, path, request):
        client = getattr(self.client, path.strip('/'))
        client.list(marker='someMarker', limit=3)
        request.assert_called_with('GET', path,
                                   options={'marker': 'someMarker',
                                            'limit': 3})

    def test_list_services_with_marker_calls_request_with_marker(self):
        return self._marker_assertion('/services')

    def test_list_events_with_marker_calls_request_with_marker(self):
        return self._marker_assertion('/events')

    def test_list_configuration_with_marker_calls_request_with_marker(self):
        return self._marker_assertion('/configuration')

    def test_list_services_with_limit_calls_request_with_limit(self):
        return self._limit_assertion('/services')

    def test_list_events_with_limit_calls_request_with_limit(self):
        return self._limit_assertion('/events')

    def test_list_configuration_with_limit_calls_request_with_limit(self):
        return self._limit_assertion('/configuration')

    def test_list_services_with_marker_and_limit(self):
        return self._marker_and_limit_assertion('/services')

    def test_list_events_with_mark_and_limit(self):
        return self._marker_and_limit_assertion('/events')

    def test_list_configuration_with_marker_and_limit(self):
        return self._marker_and_limit_assertion('/configuration')

    @mock.patch("txServiceRegistry.client.BaseClient.request")
    def test_listForTag_with_marker(self, request):
        self.client.services.listForTag('someTag', marker='someMarker')
        request.assert_called_with('GET', '/services',
                                   options={'tag': 'someTag',
                                            'marker': 'someMarker'})

    @mock.patch("txServiceRegistry.client.BaseClient.request")
    def test_listForTag_with_limit(self, request):
        self.client.services.listForTag('someTag', limit=3)
        request.assert_called_with('GET', '/services',
                                   options={'tag': 'someTag',
                                            'limit': 3})

    @mock.patch("txServiceRegistry.client.BaseClient.request")
    def test_listForTag_with_marker_and_limit(self, request):
        self.client.services.listForTag('someTag', marker='someMarker',
                                        limit=3)
        request.assert_called_with('GET', '/services',
                                   options={'tag': 'someTag',
                                            'marker': 'someMarker',
                                            'limit': 3})
