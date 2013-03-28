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

from __future__ import with_statement

import os
import sys
import subprocess
import signal
import time
import socket
import errno
import atexit

from os.path import join as pjoin

# Taken from https://github.com/Kami/python-yubico-client/blob/master/tests/utils.py
def waitForStartUp(process, address, timeout=10):
    # connect to it, with a timeout in case something went wrong
    start = time.time()
    while time.time() < start + timeout:
        try:
            s = socket.create_connection(address)
            s.close()
            break
        except:
            time.sleep(0.1)
    else:
        # see if process is still alive
        process.poll()

        if process and process.returncode is None:
            process.terminate()
        raise RuntimeError("Couldn't connect to server; aborting test")


class ProcessRunner(object):
    def setUp(self, *args, **kwargs):
        pass

    def tearDown(self, *args, **kwargs):
        if self.process:
            self.process.terminate()


class MockAPIServerRunner(ProcessRunner):
    def __init__(self, port=8881):
        self.port = port

    def setUp(self, *args, **kwargs):
        self.cwd = os.getcwd()
        self.process = None
        self.base_dir = pjoin(self.cwd)
        self.log_path = pjoin(self.cwd, 'mock_api_server.log')

        super(MockAPIServerRunner, self).setUp(*args, **kwargs)
        script = pjoin(os.path.dirname(__file__), 'mock_http_server.py')

        with open(self.log_path, 'a+') as log_fp:
            args = '%s --port=%s' % (script, str(self.port))
            fixtures_dir_arg = \
                '--fixtures-dir=txServiceRegistry/test/fixtures/response'
            args = [script, '--port=%s' % (self.port), fixtures_dir_arg]

            self.process = subprocess.Popen(args, shell=False,
                                            cwd=self.base_dir, stdout=log_fp,
                                            stderr=log_fp)
            waitForStartUp(self.process, ('127.0.0.1', self.port), 10)
        atexit.register(self.tearDown)
