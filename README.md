# Python Twisted Rackspace Service Registry client

A Twisted Python client for Rackspace Service Registry.

# License

This library is distributed under the [Apache license](http://www.apache.org/licenses/LICENSE-2.0.html).

# Usage

```Python
from txServiceRegistry import Client
from twisted.internet import reactor
from twisted.web.client import Agent

RACKSPACE_USERNAME = 'username'
RACKSPACE_KEY = 'api key'

client = Client(RACKSPACE_USERNAME, RACKSPACE_KEY)

# Do something
reactor.run()

def resultCallback(result):
    print result
    reactor.stop()
```
