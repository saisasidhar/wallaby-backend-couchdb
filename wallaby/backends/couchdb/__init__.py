# Copyright (c) by it's authors. 
# Some rights reserved. See LICENSE, AUTHORS.

from twisted.web.client import Agent
from twisted.internet import defer
from twisted.web.http_headers import Headers
from twisted.internet.protocol import Protocol
from twisted.web._newclient import ResponseFailed, ResponseDone
from twisted.python.failure import Failure
import urllib, json, base64, copy

from wallaby.backends.http import JSONProtocol, DataProducer, WebClientContextFactory, UnknownError, RawProtocol

class DocumentUpdateConflict(UnknownError):
    pass

class ViewError(UnknownError):
    pass

class ChangesProtocol(Protocol):
    def __init__(self, db, id):
        self._db = db
        self._partialbytes = None
        self._id = id
        self._closed = False

    def dataReceived(self, bytes):
        if self._partialbytes != None:
            self._partialbytes += bytes
        else:
            self._partialbytes = bytes

        self.parseData()

    def parseData(self):
        if self._partialbytes and len(self._partialbytes)>0:
            msgs = self._partialbytes.split('\n')

            self._partialbytes = msgs.pop()

            for msg in msgs:
                if len(msg) == 0: continue

                try:
                    obj = json.loads(msg)
                    self._db._newChange(self._id, obj)
                except Exception as e:
                    print "Exception while parsing", msg, e

    def close(self):
        self._closed = True
        self.transport.stopProducing()

    def connectionLost(self, reason):
        self.parseData()
        self._db._changesRunning[self._id] = False

        if self._closed: return

        if reason.type == ResponseFailed:
            self._db.removeCallbacks(self._id, close=False)

        #Reconnect
        from twisted.internet import reactor
        reactor.callLater(0, self._db.changes, self._id)

class Closer(Protocol):
    def makeConnection(self, producer):
        producer.stopProducing()

class Database(object):
    CONNECTED = 0
    DISCONNECTED = 1

    databases = {}
    defaultDB = None

    @staticmethod
    def setURLForDatabase(databaseName, url):
        database = Database.getDatabase(databaseName)
        database._url = url

    @staticmethod
    def closeDatabase(databaseName):
        if databaseName in Database.databases:
            del Database.databases[databaseName]

    @staticmethod
    def getURLForDatabase(databaseName):
        database = Database.getDatabase(databaseName)
        return database._url

    @staticmethod
    def getDefaultDatabaseName():
        return Database.defaultDB

    @staticmethod
    def setLoginForDatabase(databaseName, user, pwd):
        database = Database.getDatabase(databaseName)
        database.setCredentials(username=user, password=pwd)

    @staticmethod
    def removeLoginForDatabase(databaseName):
        database = Database.getDatabase(databaseName)
        database.setCredentials()

    @staticmethod
    def getDatabase(databaseName=None, connectionStatusCallback=None, *args, **ka):
        if databaseName == None:
            if Database.defaultDB == None or len(Database.databases) == 0: return None
            databaseName = Database.defaultDB

        if databaseName not in Database.databases:
            Database.databases[databaseName] = Database(databaseName, *args, **ka)

            if len(Database.databases) == 1:
                Database.defaultDB = databaseName

        if connectionStatusCallback:
            Database.databases[databaseName].addConnectionStatusCallback(connectionStatusCallback)

        return Database.databases[databaseName]

    @staticmethod
    def testConnectionToDatabase(databaseName):
        d = defer.Deferred()
        from twisted.internet import reactor
        reactor.callLater(0, Database._testConnectionToDatabase, d, databaseName)
        return d

    @staticmethod
    @defer.inlineCallbacks
    def _testConnectionToDatabase(d, databaseName):
        database = Database.getDatabase(databaseName)

        try:
            response = yield database.info(keepOnTrying=False, returnOnError=True)
            if 'error' in response:
                # print response
                if response['reason'] == "no_db_file":
                    yield database.create()
                    response = yield database.info(keepOnTrying=False, returnOnError=True)
                    if not 'error' in response:
                        d.callback(True)
                        return

                d.callback(False)
            else:
                d.callback(True)
        except Exception as e:
            d.errback(UnknownError(e))

    def create(self):
        return self.request("PUT", "", body=DataProducer(""))

    def destroy(self):
        return self.request('DELETE', "", body=DataProducer(""))

    def __init__(self, name, user=None, password=None, url='http://localhost:5984'):
        self._url = url
        self._name = name
        self._changesCBs = {}
        self._failedRequests = []
        self._changesRunning = {}
        self._changesProtocols = {}
        self._lastSeq = {}
        self._connectionStatusCallbacks = []
        self._connected = False
        self._user = None
        self._password = None
        self._authHeader = None

        if user != None and password != None:
            self.setCredentials(user, password)

        self._contextFactory = WebClientContextFactory()
        from twisted.internet import reactor
        self._agent = Agent(reactor, self._contextFactory)

    def name(self):
        return self._name

    def proto(self):
        if not self._url: return None
    
        m = re.match(r'(^.*?)://(.*?):(.*?)', self._url)
        if m == None: return None

        return m.group(1)

    def port(self):
        if not self._url: return None
    
        m = re.match(r'(^.*?)://(.*?):(.*?)', self._url)
        if m == None: return None

        return m.group(3)

    def host(self):
        if not self._url: return None
    
        m = re.match(r'(^.*?)://(.*?):(.*?)', self._url)
        if m == None: return None

        return m.group(2)

    def url(self):
        return self._url

    def credentials(self):
        return (self._user, self._password)

    def setCredentials(self, username=None, password=None):
        self._user = username
        self._password = password
        if username != None and password != None:
            basicAuth = base64.encodestring('%s:%s' % (username, password))
            self._authHeader = "Basic " + basicAuth.strip()

    def addConnectionStatusCallback(self, connectionStatusCallback):
        if connectionStatusCallback not in self._connectionStatusCallbacks:
            self._connectionStatusCallbacks.append(connectionStatusCallback)

    def connectionStatusChanged(self, connected):
        if self._connected != connected:
            self._connected = connected
            for connectionStatusCallback in self._connectionStatusCallbacks:
                connectionStatusCallback(connected)

    def request(self, method, path=None, body=None, headers=None, protocol=JSONProtocol, **ka):
        if headers == None and self._authHeader:
            headers = {"Authorization": [self._authHeader]}
        elif headers != None and self._authHeader:
            headers["Authorization"] = [self._authHeader]

        d = defer.Deferred()
        from twisted.internet import reactor
        reactor.callLater(0, self._request, d, method, path, body, headers, protocol, **ka)
        return d

    @defer.inlineCallbacks
    def _request(self, d, method, path, body, headers, protocol, keepOnTrying=False, returnOnError=False, **ka):
        url = self._url+"/"+self._name
        if path:
            url += "/"+urllib.quote(path)

        if len(ka) > 0:
            kv = dict()
            # print ka
            for k, v in ka.items():
                if not (isinstance(v, str) or isinstance(v, unicode) or isinstance(v, int) or isinstance(v, bool)):
                    kv[k] = json.dumps(v)
                else:
                    if isinstance(v, bool):
                        if v:
                            kv[k] = 'true'
                        else:
                            kv[k] = 'false'
                    else:
                        kv[k] = v

            url += '?'+urllib.urlencode(kv)

        try:
            # print "REQUEST", method, str(url), body
            response = yield self._agent.request(
                method,
                str(url),
                Headers(headers),
                body)

            responseDeferred = defer.Deferred()
            response.deliverBody(protocol(responseDeferred, response.length))
            responseData = yield responseDeferred
            # print responseData

            d.callback(responseData)
        except (Exception,Failure) as e:
            if keepOnTrying: #  or self._changesRunning:
                from twisted.internet import reactor
                reactor.callLater(1, self._request, d, method, path, body, headers, protocol, **ka)
            elif returnOnError:
                d.errback(e)
            else: 
                self._failedRequests.append((d, method, path, body, headers, protocol, ka))

    def connectionEstablished(self):
        self.connectionStatusChanged(Database.CONNECTED)

        failedRequests = copy.copy(self._failedRequests)
        self._failedRequests = []

        from twisted.internet import reactor
        for (d, method, path, body, headers, protocol, ka) in failedRequests:
            reactor.callLater(0, self._request, d, method, path, body, headers, protocol, **ka)

        # print "FAILED REQUESTS:", len(failedRequests)

    def assertIsDoc(self, doc):
        try:
            if doc and ('_id' in doc or 'docs' in doc):
                return True
            return False
        except:
            return False

    def assertDocHasRev(self, doc):
        try:
            if doc and '_rev' in doc:
                return True
            return False
        except:
            return False

    def assertDocHasAttachment(self, doc, filename):
        try:
            if self.assertIsDoc(doc) and  self.assertDocHasRev(doc) and '_attachments' in doc and filename in doc['_attachments']:
                return True
            return False
        except:
            return False

    def get(self, id, rev=None):
        d = defer.Deferred()

        from twisted.internet import reactor
        reactor.callLater(0, self._get, id, d, rev=rev)

        return d

    @defer.inlineCallbacks
    def _get(self, id, d, rev=None):

        if rev:
            response = yield self.request('GET', path=id, rev=rev)
        else:
            response = yield self.request('GET', path=id, conflicts=True)

        if '_id' not in response or 'error' in response:
            response = None

        d.callback(response)

    def info(self, **ka):
        return self.request('GET', **ka)

    def __error(self):
        d = defer.Deferred()
        d.errback("Assertion failed")
        return d

    def save(self, doc, **ka):
        if not self.assertIsDoc(doc): return self.__error()

        doc['wallabyUser'] = self._user #wtf?

        d = defer.Deferred()

        from twisted.internet import reactor
        reactor.callLater(0, self._save, doc, d, **ka)

        return d

    @defer.inlineCallbacks
    def _save(self, doc, d, **ka):
        jsonString = json.dumps(doc)

        if '_id' in doc:
            response = yield self.request('PUT', path=doc['_id'], body=DataProducer(jsonString), **ka)
        elif 'docs' in doc:
            response = yield self.request('POST', path='_bulk_docs', headers={'Content-Type': ['application/json']}, body=DataProducer(jsonString), **ka)

        if 'rev' in response:
            doc['_rev'] = response['rev']
            d.callback(response)
        elif 'error' in response:
            if response['error'] == 'conflict':
                if '_id' in doc: response['_id'] = doc['_id']
                if '_rev' in doc: response['_rev'] = doc['_rev']
                e = DocumentUpdateConflict(response)
            else:
                e = UnknownError(response)
            d.errback(e)
        elif 'docs' in doc:
            docs = {}
            for doc in doc['docs']:
                docs[doc['_id']] = doc

            for r in response:
                if not 'error' in r and r['id'] in docs:
                    docs[r['id']]['_rev'] = r['rev']

            d.callback(response)

    def delete(self, doc):
        if not self.assertIsDoc(doc): return self.__error()

        d = defer.Deferred()

        from twisted.internet import reactor
        reactor.callLater(0, self._delete, doc, d)

        return d

    @defer.inlineCallbacks
    def _delete(self, doc, d):
        jsonString = json.dumps(doc)

        response = yield self.request('DELETE', path=doc['_id'], rev=doc['_rev'])

        if 'error' in response:
            d.errback(UnknownError(response))
        else:
            d.callback(response)

    def delete_attachment(self, doc, filename):
        if not self.assertDocHasAttachment(doc, filename): return self.__error()

        return self.request('DELETE', path=doc['_id']+'/'+filename, rev=doc['_rev'])

    def get_attachment(self, doc, filename):
        if not self.assertDocHasAttachment(doc, filename): return self.__error()

        return self.request('GET', path=doc['_id']+'/'+filename, protocol=RawProtocol)

    def put_attachment(self, doc, filename, data, contentType='application/octet-stream'):
        if not self.assertIsDoc(doc) or not self.assertDocHasRev(doc): return self.__error()

        d = defer.Deferred()

        from twisted.internet import reactor
        reactor.callLater(0, self._put_attachment, doc, filename, data, contentType, d)

        return d

    @defer.inlineCallbacks
    def _put_attachment(self, doc, filename, data, contentType, d):
        response = yield self.request('PUT', path=doc['_id']+'/'+filename, rev=doc['_rev'], body=DataProducer(data), headers={'Content-Type':[contentType]})

        if 'rev' in response:
            doc['_rev'] = response['rev']
            d.callback(response)
        else:
            d.errback(UnknownError(response))

    def view(self, name, **ka):
        d = defer.Deferred()

        from twisted.internet import reactor
        reactor.callLater(0, self._view, name, d, **ka)

        return d

    @defer.inlineCallbacks
    def _view(self, name, d, includeCount=False, **ka):
        if 'querydoc' in ka:
            querydoc = ka['querydoc']
            del ka['querydoc']
            jsonString = json.dumps(querydoc)

            response = yield self.request('POST', path=name, headers={'Content-Type': ['application/json']}, body=DataProducer(jsonString), **ka)
        else:
            response = yield self.request('GET', path=name, **ka)

        if 'rows' in response:
            if includeCount:
                d.callback((response['rows'], response['total_rows']))
            else:
                d.callback(response['rows'])
        else:
            d.errback(ViewError((response,name)))

    def removeCallbacks(self, __id, close=True):
        # Wake up pending callbacks
        for cb in self._changesCBs[__id]:
            cb(None, viewID=__id)

        del self._changesCBs[__id]
        del self._changesRunning[__id] 
        del self._lastSeq[__id]

        if self._changesProtocols[__id] is not None and close:
            self._changesProtocols[__id].close()

        del self._changesProtocols[__id]

    def unchanges(self, cb=None, filter=None, view=None, since=None):
        __id = str(filter) + "__" + str(view)

        if __id not in self._changesCBs: return False
        if cb not in self._changesCBs[__id]: return False

        self._changesCBs[__id].remove(cb)

        if len(self._changesCBs[__id]) == 0:
            self.removeCallbacks(__id)

    @defer.inlineCallbacks
    def changes(self, cb=None, since=None, filter=None, view=None, redo=False):
        # TODO: add since to identifier
        __id = str(filter) + "__" + str(view)

        if __id not in self._changesCBs:
            # the changes stream was removed in the meanwhile...
            if redo:
                return

            self._changesCBs[__id] = []
            self._changesRunning[__id] = False
            self._lastSeq[__id] = None
            self._changesProtocols[__id] = None

        if cb:
            if cb not in self._changesCBs[__id]:
                self._changesCBs[__id].append(cb)
            else:
                return

        # TODO: Why was that here --> if not cb: #  or len(self._changesCBs) == 1:
        if since:
            self._lastSeq[__id] = since

        if self._lastSeq[__id] is None:
            info = yield self.info()

            # the changes stream was removed in the meanwhile...
            if __id not in self._lastSeq:
                return

            if 'error' in info and info['error'] == 'unauthorized':
                from twisted.internet import reactor
                reactor.callLater(1, self.changes, filter=filter, view=view, redo=True) #retry in one second
                return

            self._lastSeq[__id] = info['update_seq']

        # Request guard
        if not self._changesRunning[__id]:
            url = self._url+"/"+self._name+"/_changes?feed=continuous&since="+str(self._lastSeq[__id])+"&heartbeat=5000"

            if filter != None: url += "&filter=" + str(filter)
            if view != None: url += "&view=" + str(view)

            headers = {'User-Agent': ['Couchdb testclient'], 'Content-Type': ['text/x-greeting']}
            if self._authHeader:
                headers["Authorization"] = [self._authHeader]

            try:
                self._changesRunning[__id] = True

                response = yield self._agent.request(
                    'GET',
                    url,
                    Headers(headers), None)

                # the changes stream was removed in the meanwhile...
                if __id not in self._changesProtocols:
                    # response.deliverBody(Closer())
                    return

                self.connectionEstablished() #restart requests after lost connection

                p = ChangesProtocol(self, __id)
                response.deliverBody(p)
                self._changesProtocols[__id] = p
                # print "START changes stream", url
            except Exception as e:
                print e
                self.connectionStatusChanged(Database.DISCONNECTED)
                self._changesRunning[__id] = False
                from twisted.internet import reactor
                reactor.callLater(1, self.changes, filter=filter, view=view, redo=True) #retry in one second


    def _newChange(self, id, change):
        if 'last_seq' in change:
            self._lastSeq[id] = change['last_seq']
        else:
            for cb in self._changesCBs[id]:
                cb(change, viewID=id)
