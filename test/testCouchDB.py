# Copyright (c) by it's authors. 
# Some rights reserved. See LICENSE, AUTHORS.

from twisted.internet import defer
from twisted.trial import unittest

class WallabyCouchDBTest(unittest.TestCase):
    def setUp(self):
        self._dbName = "wallaby_test"
        self._docId  = "testdoc"

        self._designDoc = {
           "_id": "_design/wallaby_test",
           "language": "javascript",
           "views": {
               "text": {
                   "map": "function(doc) { if(doc.text)\n   emit(doc.text, null);\n}"
               }
           },
           "filters": {
               "typeB": "function(doc, req) { if((doc.type && doc.type == \"typeB\") || doc.deleted) { return true; } return false;}"
           }
        }

        import wallaby.backends.couchdb as couch
        self._db = couch.Database(self._dbName, url="http://localhost:5984")
        # self._db = couch.Database.getDatabase(self._dbName)
        # couch.Database.setURLForDatabase(self._dbName, "http://localhost:5984")

    @defer.inlineCallbacks
    def getDoc(self, name):
        doc = yield self._db.get(name)
        self.assertTrue(doc != None)
        self.assertEqual(doc["_id"], name)
        defer.returnValue(doc)

    @defer.inlineCallbacks
    def getInfo(self):
        info = yield self._db.info(keepOnTrying=False, returnOnError=True)
        self.assertEqual(info['db_name'], self._dbName)
        defer.returnValue(info)

    @defer.inlineCallbacks
    def test_00_create(self):
        try:
            info = yield self._db.info(keepOnTrying=False, returnOnError=True)
            # version = info["version"]
            # major, minor, patch = version.split(".")

            # if major < 1 or major < 2 and minor < 2:
            #     warnings.warn("Found CouchDB version " + version + ". At least version 1.2.0 is recommended")

            if info != None: self._db.destroy()
        except:
            pass

        res = yield self._db.create()
        self.assertTrue(res["ok"])

    @defer.inlineCallbacks
    def test_01_pushDesignDoc(self):
        res = yield self._db.save(self._designDoc)
        self.assertTrue(res["ok"])

    @defer.inlineCallbacks
    def test_02_load(self):
        info = yield self.getInfo()
        self.assertEqual(info["doc_count"], 1)

    @defer.inlineCallbacks
    def test_03_createDoc(self):

        doc = {"_id": self._docId, "type": "typeA", "text": "Hello World!"}
        res = yield self._db.save(doc)

        self.assertTrue(res["ok"])
        self.assertTrue("rev" in res)

    @defer.inlineCallbacks
    def test_04_loadDoc(self):
        doc = yield self.getDoc(self._docId)
        self.assertEqual(doc["text"], "Hello World!")

    @defer.inlineCallbacks
    def test_05_changes(self):
        info = yield self.getInfo()

        d = defer.Deferred()

        seq = info['update_seq']
        cb = lambda a,viewID=None: d.callback(a)

        self._db.changes(cb, since=seq)

        doc = yield self.getDoc(self._docId)

        doc["text"] = "Changed"
        res = yield self._db.save(doc)

        changed = yield d
        self.assertEqual(changed["id"], self._docId)
        self.assertEqual(changed["changes"][0]["rev"], res["rev"])

        self._db.unchanges(cb)

    @defer.inlineCallbacks
    def test_06_putAttachment(self):
        doc = yield self.getDoc(self._docId)
        yield self._db.put_attachment(doc, "test.txt", "Hello world!")

    @defer.inlineCallbacks
    def test_07_getAttachment(self):
        doc = yield self.getDoc(self._docId)
        data = yield self._db.get_attachment(doc, "test.txt")
        self.assertEqual(data, "Hello world!")

    @defer.inlineCallbacks
    def test_08_view(self):
        doc = {"_id": "doc2", "type": "typeA", "text": "text 2"}
        res = yield self._db.save(doc)

        doc = {"_id": "doc3", "type": "typeB"}
        res = yield self._db.save(doc)

        result = yield self._db.view("_design/wallaby_test/_view/text")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["key"], "Changed")
        self.assertEqual(result[1]["key"], "text 2")

        result = yield self._db.view("_design/wallaby_test/_view/text", descending=True)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[1]["key"], "Changed")
        self.assertEqual(result[0]["key"], "text 2")

    @defer.inlineCallbacks
    def test_09_viewChanges(self):
        info = yield self.getInfo()

        d = defer.Deferred()

        seq = info['update_seq']
        cb = lambda a,viewID=None: d.callback(a)

        self._db.changes(cb, since=seq, filter="_view", view="wallaby_test/text")

        doc = yield self.getDoc(self._docId)

        doc["text"] = "Changed again"
        res = yield self._db.save(doc)

        changed = yield d
        self._db.unchanges(cb, since=seq, filter="_view", view="wallaby_test/text")
        self.assertTrue(changed["id"] == self._docId)
        self.assertEqual(changed["changes"][0]["rev"], res["rev"])

    @defer.inlineCallbacks
    def test_09_filteredChanges(self):
        info = yield self.getInfo()

        d = defer.Deferred()

        seq = info['update_seq']
        cb = lambda a,viewID=None: d.callback(a)

        self._db.changes(cb, since=seq, filter="wallaby_test/typeB")

        doc = yield self.getDoc("doc3")
        doc["test"] = {"key": "value"}

        res = yield self._db.save(doc)

        changed = yield d
        self.assertTrue(changed["id"] == "doc3")
        self.assertEqual(changed["changes"][0]["rev"], res["rev"])

        self._db.unchanges(cb, since=seq, filter="wallaby_test/typeB")

    @defer.inlineCallbacks
    def test_98_deleteDoc(self):
        doc = yield self.getDoc(self._docId)
        res = yield self._db.delete(doc)
        self.assertTrue(res["ok"])

    @defer.inlineCallbacks
    def test_99_destroy(self):
        res = yield self._db.destroy()
        self.assertTrue(res["ok"])
