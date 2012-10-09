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

def resultCallback(result):
    print result
    reactor.stop()
```

## Sessions

Create a session with a heartbeat timeout of 10:

```Python
# Optional metadata (must contain string keys and values, up to 255 chars)
options = {'key': 'value'}
heartbeatTimeout = 10

d = client.sessions.create(heartbeatTimeout, options)
d.addCallback(resultCallback)
```

List sessions:

```Python
d = client.sessions.list()
d.addCallback(resultCallback)
```

Get session:

```Python
sessionId = 'seFoo'

d = client.sessions.get(sessionId)
d.addCallback(resultCallback)
```

Heartbeat a session:

```Python
sessionId = 'seFoo'
token = 'token'

d = client.sessions.heartbeat(sessionId, token)
d.addCallback(resultCallback)
```

Update existing session:

```Python
sessionId = 'seFoo'
payload = {'heartbeat_timeout': 15}

d = client.sessions.update(sessionId, payload)
d.addCallback(resultCallback)
```

## Events

List events:

```Python
marker = 'last-seen-token'

d = client.events.list(marker)
d.addCallback(resultCallback)
```

## Services

List services:

```Python

d = client.services.list()
d.addCallback(resultCallback)
```

List services for a specific tag:

```Python
tag = 'tag'

d = client.services.listForTag(tag)
d.addCallback(resultCallback)
```

Get service by ID:

```Python
serviceId = 'messenger1'

d = client.services.get(serviceId)
d.addCallback(resultCallback)
```

Create a new service:

```Python
sessionId = 'sessionId'
serviceId = 'messenger1'
payload = {
    'tags': ['messenger', 'stats'],
    'metadata': {'someKey': 'someValue', 'anotherKey': 'anotherValue'}
}

d = client.services.register(sessionId, serviceId, payload)
d.addCallback(resultCallback)
```

Update existing service:

```Python
serviceId = 'messenger1'
payload = {
    'tags': ['tag1', 'tag2'],
    'metadata': {'aKey': 'aValue'}
}

d = client.services.update(serviceId, payload)
d.addCallback(resultCallback)
```

## Configuration

List configuration values:

```Python

d = client.configuration.list()
d.addCallback(resultCallback)
```

Get configuration value by id:

```Python
configurationId = 'configId'

d = client.configuration.get(configurationId)
d.addCallback(resultCallback)
```

Update configuration value:

```Python
configurationId = 'configId'
value = 'new-value'

d = client.configuration.set(configurationId, value)
d.addCallback(resultCallback)
```

Delete configuration value:

```Python
configurationId = 'configId'

d = client.configuration.remove(configurationId)
d.addCallback(resultCallback)
```

## Accounts

Get account limits:

```Python
d = client.account.getLimits()
d.addCallback(resultCallback)
```

Also, make sure to call:

```Python
reactor.run()
```
