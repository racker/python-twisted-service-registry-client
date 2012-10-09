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

import os
import subprocess
import signal
import time
import socket
import errno
import atexit
from os.path import join as pjoin


# From https://github.com/Kami/python-yubico-client/blob/master/tests/utils.py

def waitForStartUp(process, pid, address, timeout=10):
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

        if pid and process.returncode is None:
            os.kill(pid, signal.SIGKILL)
        raise RuntimeError("Couldn't connect to server; aborting test")


class ProcessRunner(object):
    def setUp(self, *args, **kwargs):
        # clean up old.
        p = self.getPid()
        if p is not None:
            try:
                # remember, process may already be dead.
                os.kill(p, 9)
                time.sleep(0.01)
            except:
                pass

    def tearDown(self, *args, **kwargs):
        spid = self.getPid()
        if spid:
            max_wait = 1
            os.kill(spid, signal.SIGTERM)
            slept = 0
            while (slept < max_wait):
                time.sleep(0.5)
                if not self.isAlive(spid):
                    if os.path.exists(self.pid_fname):
                        os.unlink(self.pid_fname)
                    break
                slept += 0.5
            if (slept > max_wait and self.isAlive(spid)):
                os.kill(spid, signal.SIGKILL)
                if os.path.exists(self.pid_fname):
                    os.unlink(self.pid_fname)
                raise Exception('Server did not shut down correctly')
        else:
            print 'Unable to locate pid file (%s)!' % self.pid_fname

    def isAlive(self, pid):
        try:
            os.kill(pid, 0)
            return 1
        except OSError, err:
            return err.errno == errno.EPERM

    def getPid(self):
        if self.process:
            return self.process.pid
        elif os.path.exists(self.pid_fname):
            return int(open(self.pid_fname, 'r').read())
        return None


class MockAPIServerRunner(ProcessRunner):
    def __init__(self, port=8881):
        self.port = port

    def setUp(self, *args, **kwargs):
        self.cwd = os.getcwd()
        self.process = None
        self.base_dir = pjoin(self.cwd)
        self.pid_fname = pjoin(self.cwd, 'mock_api_server.pid')
        self.log_path = pjoin(self.cwd, 'mock_api_server.log')

        super(MockAPIServerRunner, self).setUp(*args, **kwargs)
        script = pjoin(os.path.dirname(__file__), 'mock_http_server.py')

        with open(self.log_path, 'a+') as log_fp:
            port_arg = '%s --port=%s' % (script, self.port)
            fixtures_dir_arg = \
                '--fixtures-dir=txServiceRegistry/test/fixtures/response'
            args = '%s %s' % (port_arg, fixtures_dir_arg)
            self.process = subprocess.Popen(args,
                                            shell=True,
                                            cwd=self.base_dir,
                                            stdout=log_fp,
                                            stderr=log_fp)
            waitForStartUp(self.process,
                           self.getPid(),
                           ('127.0.0.1', self.port), 10)
        atexit.register(self.tearDown)
