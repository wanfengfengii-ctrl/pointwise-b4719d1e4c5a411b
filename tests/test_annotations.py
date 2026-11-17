import hashlib
import json
import sqlite3
import unittest
from corpus import Corpus


class TestAnnotations(unittest.TestCase):
    def setUp(self):
        self.corpus = Corpus()
        self.text = "A\u030A😀\r\nZ"
        self.corpus.put_document("doc", self.text.encode("utf-8"))
        self.document = {"document_id": "doc", "revision": 1}

    def tearDown(self):
        self.corpus.close()

    def test_overlap(self):
        records = [
            {"id": "late", "start": 2, "end": 3, "label": {"tags": ["face"]}},
            {"id": "wide", "start": 0, "end": 3, "label": "same"},
            {"id": "same-range", "start": 0, "end": 3, "label": "same"},
            {"id": "mark", "start": 1, "end": 2, "label": None},
        ]
        expected = json.loads(json.dumps(records))
        self.assertEqual(self.corpus.put_annotations("set", self.document, records), 1)
        records[0]["label"]["tags"].append("mutated")
        self.document["revision"] = 99
        saved = self.corpus.annotations.read_revision({"set_id": "set", "revision": 1})
        self.assertEqual(saved["records"], expected)
        self.assertEqual(saved["document"], {"document_id": "doc", "revision": 1})
        payload = {"document": saved["document"], "records": expected}
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        self.assertEqual(saved["sha256"], hashlib.sha256(encoded).hexdigest())
        saved["records"][0]["label"]["tags"].clear()
        self.assertEqual(self.corpus.annotations.read_revision(
            {"set_id": "set", "revision": 1})["records"], expected)
        self.corpus.put_document("doc", b"new")
        self.assertEqual(self.corpus.put_annotations(
            "set", {"document_id": "doc", "revision": 2}, []), 2)
        self.assertEqual(self.corpus.annotations.read_revision(
            {"set_id": "set", "revision": 1})["records"], expected)

    def test_reject_whole_set(self):
        good = {"id": "ok", "start": 0, "end": 1, "label": ["x"]}
        self.assertEqual(self.corpus.put_annotations("set", self.document, [good]), 1)
        bad_records = [
            [good, {"id": "bad", "start": 0, "end": 99, "label": 0}],
            [good, {"id": "middle", "start": 1, "end": 2, "label": 0}, good],
        ]
        for start, end in ((True, 2), (0, False), (-1, 1), (2, 2), (3, 2), (0.0, 1)):
            bad_records.append([good, {"id": "bad", "start": start, "end": end, "label": 0}])
        cyclic = []
        cyclic.append(cyclic)
        for label in (float("nan"), float("inf"), {1: "bad"}, ("tuple",), cyclic, object()):
            bad_records.append([good, {"id": "bad", "start": 1, "end": 2, "label": label}])
        bad_records.extend([[good, {"id": "missing-fields"}], [good, 1]])
        for records in bad_records:
            with self.subTest(records_type=type(records).__name__):
                with self.assertRaises(ValueError):
                    self.corpus.put_annotations("set", self.document, records)
                head = self.corpus.connection.execute(
                    "SELECT head FROM annotation_heads WHERE set_id='set'").fetchone()[0]
                self.assertEqual(head, 1)
        with self.assertRaises(KeyError):
            self.corpus.put_annotations(
                "new", {"document_id": "missing", "revision": 1}, [good])
        with self.assertRaises(KeyError):
            self.corpus.put_annotations(
                "set", {"document_id": "doc", "revision": 99}, [good])
        with self.assertRaises(ValueError):
            self.corpus.put_annotations("new", self.document, bad_records[0])
        with self.assertRaises(KeyError):
            self.corpus.annotations.read_revision({"set_id": "new", "revision": 1})
        self.assertEqual(self.corpus.put_annotations("set", self.document, []), 2)
        empty = self.corpus.annotations.read_revision({"set_id": "set", "revision": 2})
        self.assertEqual(empty["records"], [])
        self.assertEqual(empty["document"], self.document)
        self.assertEqual(self.corpus.put_annotations("new", self.document, []), 1)

    def test_storage_failure(self):
        self.corpus.put_annotations("set", self.document, [])
        self.corpus.connection.execute("""
            CREATE TRIGGER reject_annotation AFTER INSERT ON annotation_records
            BEGIN SELECT RAISE(ABORT, 'annotation_boundary'); END
        """)
        record = {"id": "a", "start": 2, "end": 3, "label": True}
        with self.assertRaisesRegex(sqlite3.IntegrityError, "annotation_boundary"):
            self.corpus.put_annotations("set", self.document, [record])
        self.assertEqual(self.corpus.annotations.read_revision(
            {"set_id": "set", "revision": 1})["records"], [])
        with self.assertRaises(KeyError):
            self.corpus.annotations.read_revision({"set_id": "set", "revision": 2})
        self.corpus.connection.execute("DROP TRIGGER reject_annotation")
        self.assertEqual(self.corpus.put_annotations("set", self.document, [record]), 2)
