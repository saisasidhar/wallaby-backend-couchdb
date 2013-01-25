Wallaby backend for CouchDB
===========================

This package provides an asynchronous python interface to CouchDB (using twisted).

For more information on wallaby visit http://wlby.freshx.de

Installation
============

You can install the couchdb backend with pip

```bash
pip install wallaby-backend-couchdb
```

How to use
==========

The library is based on twisted's asynchronous pattern. To use the library in an asynchronous fassion you 
first need to create an reactor based application:
 
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

Now we can connect to an existing CouchDB database:

```python
@defer.inlineCallbacks
def run():
    # Create database client object
    from wallaby.backends.couchdb import Database
    db = Database(
        "<name of database>", 
        username="<username>", 
        password="<password>", 
        url="http://localhost:5984"
    )

    # Query database info in an async manner
    info = yield db.info()

    # Output the info dict
    print info

    # <----- More example Code paste here

    # stop the reactor and quit the application
    reactor.stop()
```

Create and delete database
--------------------------

With the required permissions you could easily create and destroy databases

```python
    newdb = Database(
        "<name of new database>", 
        username="<username>", 
        password="<password>", 
        url="http://localhost:5984"
    )

    # Create the new database 
    res = yield newdb.create()

    # Destroy the new database
    res = yield newdb.destroy()
```

Read and write document
-----------------------

```python
    # Get a document by id
    doc = yield db.get('docid')

    # add a new value to the document
    doc['test'] = 'Hello World'

    # save the document
    res = yield db.save(doc)
```

Creating and deleting documents
-------------------------------

```python
    # Create a new doc
    doc = {'_id': 'newdocid'}
    res = yield db.save(doc)

    # the result contains the response from the CouchDB server
    if not 'error' in res:
        # the document was saved successfully. The new revision was updated in the "_rev" field of doc.
        print doc['_rev']

        # delete the document
        res = yield db.delete(doc)
```

Attachment handling
-------------------

```python
    # First we a load a file to attach. In real life you should do this in an async manner
    content = open('test.png').read()

    # Now we can attach this file to an existing document
    res = yield db.put_attachment(doc, 'newimage.png', content, content-type='image/png')

    # And load from database again
    content = yield db.get_attachment(doc, 'newimage.png')

    # and finally delete it
    res = yield db.delete_attachment(doc, 'newimage.png')
```

Views
-----

```python
    # get all rows of view
    rows = yield db.view('_design/designname/_view/viewname')

    # pass view arguments
    rows = yield db.view('_design/designname/_view/viewname', count=100)
```

Changes
-------

```python
    def callback(changes, viewID=None):
        # all changes are passed to this callback as an array. the viewID help to identify 
        # view-based changes
        pass

    # register callback function for filtered changes
    db.changes(cb=callback, since=12345, filter="couchappdoc/all")

    # register callback function for view changes (only works in CouchDB 1.2)
    db.changes(cb=callback, since=12345, filter="_view", view="couchappdoc/viewname")

    # unregister first callback
    db.unchanges(since=12345, filter="couchappdoc/all")

    # unregister second callback
    db.changes(since=12345, filter="_view", view="couchappdoc/viewname")
```

