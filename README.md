Wallaby backend for CouchDB
===========================

This package provides an asynchronous python interface to CouchDB (using twisted).

Installation
============

You can install the couchdb backend with pip

```bash
pip install wallaby-backend-couchdb
```

How to use
==========

The library is based on twisted's asynchronous pattern. The use the library in an asynchronous fassion you first need to create
an reactor based application
 
```python
from twisted.internet import defer

@defer.inlineCallbacks
def run():
    # wait 1 second
    d = defer.Deferred()
    reactor.callLater(1.0, d.callback)
    yield d

    # stop the reactor and quit the application
    reactor.stop()

from twisted.internet import reactor
reactor.callWhenRunning(run)
reactor.run()
```

Now we can connect to an existing CouchDB database

```python
@defer.inlineCallbacks
def run():
    # Create database client object
    from wallaby.backends.couchdb import Database
    db = Database("<name of database>", username="<username>", password="<password>", url="http://localhost:5984")

    # Query database info in an async manner
    info = yield db.info()

    # Output the info dict
    print info

    # stop the reactor and quit the application
    reactor.stop()
```
