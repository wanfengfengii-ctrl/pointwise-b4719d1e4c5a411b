import hashlib
import sqlite3
import unittest
from corpus import Corpus


class TestCapture(unittest.TestCase):
    def setUp(self):
        self.corpus = Corpus()

    def tearDown(self):
        self.corpus.close()

    def test_unicode_revision(self):
        sources = ["A\u030A😀", "\ufeffA\r\nB\n", "", "a\u0315\u0300"]
        for revision, text in enumerate(sources, 1):
            raw = text.encode("utf-8")
            self.assertEqual(self.corpus.put_document("doc", raw), revision)
            ref = {"document_id": "doc", "revision": revision}
            saved = self.corpus.documents.read_revision(ref)
            self.assertEqual(saved["text"], text)
            self.assertEqual(saved["utf8_bytes"], raw)
            self.assertEqual(saved["source_sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(saved["codepoint_count"], len(text))
            saved["text"] = "changed"
            self.assertEqual(self.corpus.documents.read_revision(ref)["text"], text)
        self.assertEqual(self.corpus.put_document("doc", b""), 5)
        self.assertEqual(self.corpus.documents.latest_revision("doc"), 5)
        self.assertEqual(self.corpus.documents.read_revision(
            {"document_id": "doc", "revision": 1})["text"], sources[0])

    def test_invalid_utf8(self):
        self.assertEqual(self.corpus.put_document("doc", b"old"), 1)
        for raw in (b"\xff", b"\xc0\xaf", b"\xed\xa0\x80", "text", bytearray(b"x")):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    self.corpus.put_document("doc", raw)
                self.assertEqual(self.corpus.documents.latest_revision("doc"), 1)
        with self.assertRaises(ValueError):
            self.corpus.put_document("new", b"\xff")
        with self.assertRaises(KeyError):
            self.corpus.documents.latest_revision("new")
        self.assertEqual(self.corpus.put_document("doc", b"next"), 2)

    def test_storage_failure_and_missing_reference(self):
        self.corpus.put_document("doc", b"old")
        connection = self.corpus.connection
        connection.execute("""
            CREATE TRIGGER reject_document AFTER INSERT ON document_revisions
            BEGIN SELECT RAISE(ABORT, 'document_boundary'); END
        """)
        with self.assertRaisesRegex(sqlite3.IntegrityError, "document_boundary"):
            self.corpus.put_document("doc", b"new")
        with self.assertRaises(sqlite3.IntegrityError):
            self.corpus.put_document("new", b"new")
        self.assertEqual(self.corpus.documents.latest_revision("doc"), 1)
        with self.assertRaises(KeyError):
            self.corpus.documents.latest_revision("new")
        connection.execute("DROP TRIGGER reject_document")
        self.assertEqual(self.corpus.put_document("doc", b"new"), 2)
        for ref in ({"document_id": "missing", "revision": 1},
                    {"document_id": "doc", "revision": 99}):
            with self.assertRaises(KeyError):
                self.corpus.documents.read_revision(ref)
        for ref in (1, {"document_id": "doc", "revision": True}):
            with self.assertRaises(ValueError):
                self.corpus.documents.read_revision(ref)
        for identity in ("", None, 1):
            with self.assertRaises(ValueError):
                self.corpus.put_document(identity, b"x")
