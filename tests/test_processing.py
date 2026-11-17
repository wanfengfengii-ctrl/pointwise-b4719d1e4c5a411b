import random
import unittest
from corpus import Corpus


class TestProcessing(unittest.TestCase):
    def setUp(self):
        self.corpus = Corpus()
        self.text = "A\u030A😀\r\nZ"
        self.corpus.put_document("doc", self.text.encode("utf-8"))
        self.doc = {"document_id": "doc", "revision": 1}
        self.records = [
            {"id": "face", "start": 2, "end": 3, "label": {"class": ["emoji"]}},
            {"id": "whole", "start": 0, "end": 5, "label": "wide"},
            {"id": "mark", "start": 1, "end": 2, "label": "accent"},
            {"id": "newline", "start": 3, "end": 5, "label": None},
        ]
        self.corpus.put_annotations("set", self.doc, self.records)
        self.ann = {"set_id": "set", "revision": 1}

    def tearDown(self):
        self.corpus.close()

    def assert_no_publications(self):
        for table in ("datasets", "dataset_rows", "request_receipts"):
            self.assertEqual(self.corpus.connection.execute(
                "SELECT COUNT(*) FROM " + table).fetchone()[0], 0)

    def test_revision_mismatch(self):
        self.corpus.put_document("doc", self.text.encode("utf-8"))
        self.corpus.put_document("other", self.text.encode("utf-8"))
        for ref in ({"document_id": "doc", "revision": 2},
                    {"document_id": "other", "revision": 1}):
            with self.assertRaises(ValueError):
                self.corpus.build_raw("request", ref, self.ann)
            self.assert_no_publications()
        with self.assertRaises(KeyError):
            self.corpus.build_raw("request", {"document_id": "doc", "revision": 99}, self.ann)
        with self.assertRaises(KeyError):
            self.corpus.build_raw("request", self.doc, {"set_id": "set", "revision": 99})
        with self.assertRaises(ValueError):
            self.corpus.build_raw("", self.doc, self.ann)
        self.assert_no_publications()

    def test_raw_rows_and_replay(self):
        self.corpus.put_document("doc", b"new")
        self.corpus.put_annotations("set", {"document_id": "doc", "revision": 2}, [
            {"id": "new", "start": 0, "end": 3, "label": "new"}])
        dataset_id = self.corpus.build_raw("request", self.doc, self.ann)
        saved = self.corpus.read(dataset_id)
        expected = [
            {"annotation_id": item["id"], "start": item["start"], "end": item["end"],
             "label": item["label"], "text": self.text[item["start"]:item["end"]]}
            for item in self.records]
        self.assertEqual(saved["rows"], expected)
        self.assertEqual(saved["kind"], "raw_v1")
        self.assertEqual(saved["inputs"]["document"]["revision"], 1)
        self.assertEqual(saved["inputs"]["annotations"]["revision"], 1)
        self.assertEqual(self.corpus.build_raw("request", self.doc, self.ann), dataset_id)
        self.corpus.put_annotations("set", self.doc, self.records)
        with self.assertRaises(ValueError):
            self.corpus.build_raw("request", self.doc, {"set_id": "set", "revision": 3})
        with self.assertRaises(ValueError):
            self.corpus.build_raw("request", {"document_id": "doc", "revision": 2},
                                  {"set_id": "set", "revision": 2})
        self.assertEqual(self.corpus.connection.execute(
            "SELECT COUNT(*) FROM datasets").fetchone()[0], 1)
        self.assertEqual(self.corpus.read(dataset_id), saved)
        self.corpus.put_annotations("empty", self.doc, [])
        empty_ref = {"set_id": "empty", "revision": 1}
        empty_id = self.corpus.build_raw("empty-request", self.doc, empty_ref)
        self.assertEqual(self.corpus.read(empty_id)["rows"], [])
        self.assertEqual(self.corpus.export(empty_id)["jsonl"], "")
        self.assertEqual(self.corpus.build_raw("empty-request", self.doc, empty_ref), empty_id)

    def test_independent_slices(self):
        generator = random.Random(117)
        for index in range(20):
            text = "".join(generator.choice("A\u030A😀\r\nq\u0315\u0300") for _ in range(30))
            revision = self.corpus.put_document("random", text.encode("utf-8"))
            doc = {"document_id": "random", "revision": revision}
            records = []
            for ordinal in range(12):
                start = generator.randrange(len(text))
                end = generator.randrange(start + 1, len(text) + 1)
                records.append({"id": str(ordinal), "start": start, "end": end,
                                "label": [ordinal, {"text": "标签\n"}]})
            ann_revision = self.corpus.put_annotations("random", doc, records)
            dataset_id = self.corpus.build_raw(
                "random-" + str(index), doc, {"set_id": "random", "revision": ann_revision})
            rows = self.corpus.read(dataset_id)["rows"]
            self.assertEqual([row["annotation_id"] for row in rows], [r["id"] for r in records])
            self.assertEqual([row["text"] for row in rows],
                             [text[r["start"]:r["end"]] for r in records])

    def test_candidate_rejection_and_missing_dataset(self):
        dataset_id = self.corpus.build_raw("valid", self.doc, self.ann)
        saved = self.corpus.read(dataset_id)
        for rows in (saved["rows"][:-1], saved["rows"] + saved["rows"][:1]):
            with self.assertRaises(ValueError):
                self.corpus.datasets.publish_raw("invalid", saved["inputs"], rows)
        with self.assertRaises(KeyError):
            self.corpus.read("missing")
        with self.assertRaises(KeyError):
            self.corpus.export("missing")
        self.assertEqual(self.corpus.connection.execute(
            "SELECT COUNT(*) FROM request_receipts").fetchone()[0], 1)
