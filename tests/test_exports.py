import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from corpus import Corpus


class TestExports(unittest.TestCase):
    def _publish(self, corpus):
        text = '\ufeffA\u030A😀\r\n"\\\x01尾\u2028'
        corpus.put_document("doc", text.encode("utf-8"))
        document = {"document_id": "doc", "revision": 1}
        records = [
            {"id": "whole", "start": 0, "end": len(text),
             "label": {"nested": ["LF\nCR\r", '"\\\x02', 0, False, None]}},
            {"id": "face", "start": 3, "end": 4, "label": "😀"},
        ]
        corpus.put_annotations("set", document, records)
        return corpus.build_raw("request", document, {"set_id": "set", "revision": 1})

    def _audit(self, saved, exported):
        jsonl = exported["jsonl"]
        raw = jsonl.encode("utf-8")
        parts = raw.split(b"\n")
        self.assertEqual(parts[-1], b"")
        self.assertEqual(len(parts) - 1, len(saved["rows"]))
        objects = [json.loads(part) for part in parts[:-1]]
        expected_keys = [
            "dataset_id", "document_id", "document_revision", "annotation_set_id",
            "annotation_revision", "annotation_id", "start", "end", "label", "text"]
        for actual, row in zip(objects, saved["rows"]):
            self.assertEqual(list(actual), expected_keys)
            self.assertEqual(actual["dataset_id"], saved["dataset_id"])
            self.assertEqual(actual["document_id"], saved["inputs"]["document"]["document_id"])
            self.assertEqual(actual["document_revision"], saved["inputs"]["document"]["revision"])
            self.assertEqual(actual["annotation_set_id"], saved["inputs"]["annotations"]["set_id"])
            self.assertEqual(actual["annotation_revision"], saved["inputs"]["annotations"]["revision"])
            for key in ("annotation_id", "start", "end", "label", "text"):
                self.assertEqual(actual[key], row[key])
        payload = {key: saved[key] for key in ("kind", "inputs", "rows")}
        content = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        manifest = exported["manifest"]
        self.assertEqual(manifest, {
            "dataset_id": saved["dataset_id"], "kind": "raw_v1",
            "inputs": saved["inputs"], "row_count": len(saved["rows"]),
            "content_sha256": hashlib.sha256(content).hexdigest(),
            "jsonl_sha256": hashlib.sha256(raw).hexdigest(),
        })
        self.assertEqual(saved["content_sha256"], manifest["content_sha256"])

    def test_jsonl_framing_and_detached_values(self):
        with Corpus() as corpus:
            dataset_id = self._publish(corpus)
            saved, exported = corpus.read(dataset_id), corpus.export(dataset_id)
            self._audit(saved, exported)
            changed = corpus.read(dataset_id)
            changed["rows"][0]["label"]["nested"].append("external")
            changed["rows"].pop()
            changed["inputs"]["document"]["revision"] = 900
            changed_export = corpus.export(dataset_id)
            changed_export["manifest"]["inputs"]["annotations"]["revision"] = 900
            self.assertEqual(corpus.read(dataset_id), saved)
            self.assertEqual(corpus.export(dataset_id), exported)
            document = {"document_id": "doc", "revision": 1}
            corpus.put_annotations("empty", document, [])
            empty_id = corpus.build_raw(
                "empty", document, {"set_id": "empty", "revision": 1})
            empty = corpus.export(empty_id)
            self.assertEqual(empty["jsonl"], "")
            self.assertEqual(empty["manifest"]["row_count"], 0)
            self.assertEqual(empty["manifest"]["jsonl_sha256"], hashlib.sha256(b"").hexdigest())

    def test_frozen_export_after_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "corpus.sqlite")
            with Corpus(path) as corpus:
                dataset_id = self._publish(corpus)
                saved, exported = corpus.read(dataset_id), corpus.export(dataset_id)
                self._audit(saved, exported)
                corpus.put_document("doc", b"new")
                corpus.put_annotations("set", {"document_id": "doc", "revision": 2}, [
                    {"id": "new", "start": 0, "end": 3, "label": ["new"]}])
            with Corpus(path) as corpus:
                self.assertEqual(corpus.read(dataset_id), saved)
                self.assertEqual(corpus.export(dataset_id), exported)
                self._audit(corpus.read(dataset_id), corpus.export(dataset_id))
                self.assertEqual(corpus.build_raw(
                    "request", {"document_id": "doc", "revision": 1},
                    {"set_id": "set", "revision": 1}), dataset_id)
                source = corpus.documents.read_revision({"document_id": "doc", "revision": 1})
                self.assertEqual(source["source_sha256"],
                                 hashlib.sha256(source["utf8_bytes"]).hexdigest())
                annotation = corpus.annotations.read_revision({"set_id": "set", "revision": 1})
                self.assertEqual(annotation["document"], {"document_id": "doc", "revision": 1})
