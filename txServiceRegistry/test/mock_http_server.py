#!/usr/bin/env python

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


import BaseHTTPServer
import os
import re

from optparse import OptionParser

mock_action = None
signature = None

HTTP_GET_PATHS = {
    '/sessions': {'fixture_path': 'sessions-get.json'},
    '/sessions/sessionId': {'fixture_path': 'sessions-sessionId-get.json'},
    '/limits': {'fixture_path': 'limits-get.json'},
    '/events': {'fixture_path': 'events-get.json'},
    '/configuration': {'fixture_path': 'configuration-get.json'},
    '/configuration/configId':
    {'fixture_path': 'configuration-configId-get.json'},
    '/services': {'fixture_path': 'services-get.json'},
    '/services/dfw1-db1':
    {'fixture_path': 'services-dfw1-db1-get.json'},
    '/services?tag=db': {'fixture_path': 'services-tag-db-get.json'},
}

HTTP_POST_PATHS = {
    '/sessions':
    {'fixture_path': 'sessions-post.json',
     'headers': {'Location': '127.0.0.1/v1.0/7777/sessions/sessionId'}},
    '/sessions/sessionId/heartbeat':
    {'fixture_path': 'sessions-sessionId-heartbeat-post.json',
     'status_code': 200},
    '/services':
    {'headers': {'Location': '127.0.0.1/v1.0/7777/services/dfw1-db1'}}
}

usage = 'usage: %prog --port=<port> --fixtures-dir=<fixtures directory>'
parser = OptionParser(usage=usage)
parser.add_option("--port", dest='port', default=8881,
                  help='Port to listen on', metavar='PORT')
parser.add_option("--fixtures-dir", dest='fixtures_dir',
                  default='fixtures/response/',
                  help='The folder in which JSON response fixtures'
                       ' for the tests live')

(options, args) = parser.parse_args()


class Handler(BaseHTTPServer.BaseHTTPRequestHandler):

    def _read_fixture(self, path):
        fixture_path = os.path.join(options.fixtures_dir, path)
        with open(fixture_path, 'r') as f:
            fixture = f.read()

        return fixture

    def _setup_response(self, method_dict, status_code):
        split_path = re.split('(\W)', self.path)
        path = ''.join(split_path[3:])
        if path in method_dict:
            fixture_path = method_dict[path].get('fixture_path', None)
            status_code = method_dict[path].get('status_code', status_code)
            headers = method_dict[path].get('headers', None)
            body = self._read_fixture(fixture_path) if fixture_path else ''

            return self._end(status_code=status_code,
                             headers=headers,
                             body=body)

    def do_GET(self):
        return self._setup_response(HTTP_GET_PATHS, 200)

    def do_POST(self):
        return self._setup_response(HTTP_POST_PATHS, 201)

    def do_PUT(self):
        if 'sessions' in self.path:
            headers = \
                {'Location': '127.0.0.1/v1.0/7777/sessions/sessionId'}
            return self._end(status_code=204, headers=headers)
        elif 'services' in self.path:
            headers = \
                {'Location': '127.0.0.1/v1.0/7777/services/dfw1-db1'}
            return self._end(status_code=204, headers=headers)

    def do_DELETE(self):
        return self._end(status_code=204)

    def _end(self, status_code=200, headers=None, body=''):
        print 'Sending response: status_code=%s, body=%s' % (status_code, body)
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        if headers:
            for key, value in headers.iteritems():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)


def main():
    server_class = BaseHTTPServer.HTTPServer
    httpd = server_class(('127.0.0.1', int(options.port)), Handler)
    print 'Mock API server listening on 127.0.0.1:%s' % (options.port)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass

    httpd.server_close()

main()
