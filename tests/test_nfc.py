import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from corpus import Corpus
from corpus.processing.normalize import nfc_with_origins, project_spans
from nfc_examples import CASES, canonical, expected_annotations, prepare


def build(corpus, case, identity, request):
    document, annotations = prepare(corpus, case, identity)
    dataset_id = corpus.build_nfc(request, document, annotations)
    return document, annotations, dataset_id


class TestNormalize(unittest.TestCase):
    def test_fixtures_match_contract(self):
        for source, text, origins, _ in CASES:
            normalized, actual_origins = nfc_with_origins(source)
            self.assertEqual(normalized, text)
            self.assertEqual(actual_origins, origins)
            for source_list in actual_origins:
                self.assertEqual(source_list, sorted(set(source_list)))

    def test_project_spans_are_maximal(self):
        _, origins = nfc_with_origins("q̀̕")
        self.assertEqual(origins, [[0], [2], [1]])
        self.assertEqual(project_spans(origins, 0, 2), [[0, 1], [2, 3]])
        self.assertEqual(project_spans(origins, 1, 3), [[1, 3]])

    def test_whole_range_oracle(self):
        import random
        import unicodedata
        rng = random.Random(404)
        for _ in range(2000):
            count = rng.randrange(12)
            text = "".join(chr(rng.randrange(0x110000)) for _ in range(count))
            normalized, origins = nfc_with_origins(text)
            self.assertEqual(normalized, unicodedata.normalize("NFC", text))
            self.assertEqual(len(normalized), len(origins))
            if count:
                self.assertEqual(
                    sorted({index for source in origins for index in source}),
                    list(range(count)))


class TestNfcPublication(unittest.TestCase):
    def test_read_shape_digest_and_export(self):
        case = CASES[7]
        with Corpus() as corpus:
            document, annotations, dataset_id = build(corpus, case, "doc", "request")
            saved = corpus.read(dataset_id)
            self.assertEqual(set(saved), {
                "dataset_id", "kind", "inputs", "text", "origins",
                "annotations", "content_sha256"})
            self.assertEqual(saved["kind"], "nfc_v1")
            self.assertEqual(saved["text"], case[1])
            self.assertEqual(saved["origins"], case[2])
            self.assertEqual(saved["annotations"], expected_annotations(case))
            digest = hashlib.sha256(canonical({
                "kind": "nfc_v1", "inputs": saved["inputs"],
                "text": saved["text"], "origins": saved["origins"],
                "annotations": saved["annotations"]})).hexdigest()
            self.assertEqual(saved["content_sha256"], digest)
            exported = corpus.export(dataset_id)
            record = json.loads(exported["jsonl"])
            self.assertEqual(list(record), [
                "dataset_id", "kind", "inputs", "text", "origins", "annotations"])
            self.assertTrue(exported["jsonl"].endswith("\n"))
            self.assertEqual(exported["manifest"]["row_count"], 1)
            self.assertEqual(exported["manifest"]["content_sha256"], digest)
            self.assertEqual(
                exported["manifest"]["jsonl_sha256"],
                hashlib.sha256(exported["jsonl"].encode("utf-8")).hexdigest())

    def test_empty_document_is_real_dataset(self):
        with Corpus() as corpus:
            revision = corpus.put_document("empty", b"")
            document = {"document_id": "empty", "revision": revision}
            ann_revision = corpus.put_annotations("empty", document, [])
            dataset_id = corpus.build_nfc(
                "empty-nfc", document, {"set_id": "empty", "revision": ann_revision})
            saved = corpus.read(dataset_id)
            self.assertEqual(saved["text"], "")
            self.assertEqual(saved["origins"], [])
            self.assertEqual(saved["annotations"], [])
            exported = corpus.export(dataset_id)
            self.assertEqual(exported["jsonl"].count("\n"), 1)
            self.assertEqual(exported["manifest"]["row_count"], 1)

    def test_shared_characters_and_discontinuous_spans(self):
        case = CASES[0]
        with Corpus() as corpus:
            document, annotations, dataset_id = build(corpus, case, "shared", "request")
            saved = corpus.read(dataset_id)
            self.assertEqual([item["spans"] for item in saved["annotations"]],
                             [[[0, 1]], [[0, 1]]])
            self.assertEqual(saved["annotations"][0]["annotation_id"], "0")
            self.assertEqual(saved["annotations"][1]["annotation_id"], "1")

    def test_replay_and_kind_conflicts(self):
        case = CASES[1]
        with Corpus() as corpus:
            document, annotations, dataset_id = build(corpus, case, "doc", "same")
            self.assertEqual(corpus.build_nfc("same", document, annotations), dataset_id)
            self.assertEqual(
                corpus.processing.build_nfc("same", document, annotations), dataset_id)
            with self.assertRaises(ValueError):
                corpus.build_raw("same", document, annotations)
            raw_id = corpus.build_raw("raw-request", document, annotations)
            with self.assertRaises(ValueError):
                corpus.build_nfc("raw-request", document, annotations)
            self.assertEqual(corpus.read(raw_id)["kind"], "raw_v1")
            with self.assertRaises(KeyError):
                corpus.build_nfc(
                    "missing", {"document_id": "doc", "revision": 99}, annotations)
            with self.assertRaises(ValueError):
                corpus.build_nfc("", document, annotations)

    def test_binding_conflict_leaves_no_receipt(self):
        case = CASES[2]
        with Corpus() as corpus:
            document, annotations, _ = build(corpus, case, "doc", "first")
            corpus.put_document("doc", b"replaced")
            newer = {"document_id": "doc", "revision": 2}
            ann_revision = corpus.put_annotations("doc", newer, [
                {"id": "new", "start": 0, "end": 1, "label": "new"}])
            new_annotations = {"set_id": "doc", "revision": ann_revision}
            with self.assertRaises(ValueError):
                corpus.build_nfc("conflict", newer, annotations)
            with self.assertRaises(KeyError):
                corpus.build_nfc(
                    "missing-doc", newer,
                    {"set_id": "doc", "revision": 99})
            self.assertIsNone(corpus.connection.execute(
                "SELECT 1 FROM request_receipts WHERE request_id IN ('conflict','missing-doc')"
            ).fetchone())

    def test_write_failure_rolls_back_and_retries(self):
        case = CASES[3]
        with Corpus() as corpus:
            document, annotations, dataset_id = build(corpus, case, "doc", "kept")
            corpus.connection.execute("PRAGMA query_only=ON")
            try:
                with self.assertRaises(sqlite3.OperationalError):
                    corpus.build_nfc("retry", document, annotations)
            finally:
                corpus.connection.execute("PRAGMA query_only=OFF")
            self.assertFalse(corpus.connection.in_transaction)
            retry_id = corpus.build_nfc("retry", document, annotations)
            self.assertEqual(corpus.build_nfc("retry", document, annotations), retry_id)
            self.assertEqual(corpus.read(retry_id), corpus.read(retry_id))
            self.assertEqual(
                corpus.connection.execute(
                    "SELECT COUNT(*) FROM request_receipts WHERE request_id='retry'").fetchone()[0],
                1)
            self.assertEqual(corpus.read(dataset_id)["kind"], "nfc_v1")

    def test_sqlite_trigger_failure_is_atomic(self):
        case = CASES[4]
        with Corpus() as corpus:
            document, annotations, dataset_id = build(corpus, case, "doc", "kept")
            before = tuple(corpus.connection.execute(
                "SELECT COUNT(*) FROM " + table).fetchone()[0]
                for table in ("datasets", "dataset_rows", "request_receipts"))
            for index, boundary in enumerate((
                    "AFTER INSERT ON datasets BEGIN SELECT RAISE(ABORT, 'nfc_boundary'); END",
                    "AFTER INSERT ON request_receipts "
                    "BEGIN SELECT RAISE(ABORT, 'nfc_boundary'); END")):
                with self.subTest(boundary=index):
                    corpus.connection.execute(
                        "CREATE TRIGGER reject_nfc " + boundary)
                    request = "trigger-retry-" + str(index)
                    with self.assertRaises(sqlite3.IntegrityError):
                        corpus.build_nfc(request, document, annotations)
                    self.assertFalse(corpus.connection.in_transaction)
                    self.assertIsNone(corpus.connection.execute(
                        "SELECT 1 FROM request_receipts WHERE request_id=?",
                        (request,)).fetchone())
                    corpus.connection.execute("DROP TRIGGER reject_nfc")
                    retry_id = corpus.build_nfc(request, document, annotations)
                    self.assertEqual(
                        corpus.build_nfc(request, document, annotations), retry_id)
            after = tuple(corpus.connection.execute(
                "SELECT COUNT(*) FROM " + table).fetchone()[0]
                for table in ("datasets", "dataset_rows", "request_receipts"))
            self.assertEqual(after, tuple(value + 2 for value in before))
            self.assertEqual(corpus.read(dataset_id)["kind"], "nfc_v1")

    def test_detached_snapshot_and_export_values(self):
        case = CASES[5]
        with Corpus() as corpus:
            document, annotations, dataset_id = build(corpus, case, "doc", "request")
            saved = corpus.read(dataset_id)
            exported = corpus.export(dataset_id)
            saved["origins"].append([99])
            saved["annotations"][0]["spans"].clear()
            exported["manifest"]["inputs"]["document"]["revision"] = 99
            self.assertEqual(corpus.read(dataset_id), corpus.read(dataset_id))
            fresh = corpus.read(dataset_id)
            self.assertEqual(fresh["origins"], case[2])
            self.assertTrue(all(item["spans"] for item in fresh["annotations"]))

    def test_upstream_replacement_and_reopen_keep_history(self):
        case = CASES[2]
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "corpus.sqlite")
            with Corpus(path) as corpus:
                document, annotations, dataset_id = build(corpus, case, "doc", "request")
                before_read = corpus.read(dataset_id)
                before_export = corpus.export(dataset_id)
                corpus.put_document("doc", b"replacement")
                newer = {"document_id": "doc", "revision": 2}
                ann_revision = corpus.put_annotations("doc", newer, [])
                new_annotations = {"set_id": "doc", "revision": ann_revision}
                with self.assertRaises(ValueError):
                    corpus.build_nfc("request", newer, new_annotations)
            with Corpus(path) as corpus:
                self.assertEqual(corpus.read(dataset_id), before_read)
                self.assertEqual(corpus.export(dataset_id), before_export)
                self.assertEqual(corpus.build_nfc("request", document, annotations),
                                 dataset_id)

    def test_raw_chain_remains_available_alongside_nfc(self):
        case = CASES[0]
        with Corpus() as corpus:
            document, annotations = prepare(corpus, case, "doc")
            raw_id = corpus.build_raw("raw", document, annotations)
            nfc_id = corpus.build_nfc("nfc", document, annotations)
            self.assertEqual(
                corpus.read(raw_id)["inputs"], corpus.read(nfc_id)["inputs"])
            self.assertEqual(corpus.read(raw_id)["kind"], "raw_v1")
            self.assertEqual(corpus.read(nfc_id)["kind"], "nfc_v1")
            self.assertNotEqual(raw_id, nfc_id)


if __name__ == "__main__":
    unittest.main()
