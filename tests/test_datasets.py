from pathlib import Path
import sqlite3
import tempfile
import unittest
from corpus import Corpus


class TestDatasets(unittest.TestCase):
    def _exercise(self, path, reopen):
        corpus = Corpus(path)
        try:
            corpus.put_document("doc", "A\u030A😀".encode("utf-8"))
            document = {"document_id": "doc", "revision": 1}
            records = [
                {"id": "a", "start": 0, "end": 1, "label": {"v": [1]}},
                {"id": "b", "start": 1, "end": 3, "label": "tail"},
            ]
            corpus.put_annotations("set", document, records)
            annotations = {"set_id": "set", "revision": 1}
            original_id = corpus.build_raw("original", document, annotations)
            original = corpus.read(original_id)
            corpus.connection.execute("""
                CREATE TABLE deferred_guard (
                    dataset_id TEXT REFERENCES datasets(dataset_id)
                    DEFERRABLE INITIALLY DEFERRED
                )
            """)
            boundaries = [
                "AFTER INSERT ON datasets BEGIN SELECT RAISE(ABORT, 'publication_boundary'); END",
                "BEFORE INSERT ON dataset_rows WHEN NEW.ordinal=1 "
                "BEGIN SELECT RAISE(ABORT, 'publication_boundary'); END",
                "BEFORE INSERT ON request_receipts "
                "BEGIN SELECT RAISE(ABORT, 'publication_boundary'); END",
                "AFTER INSERT ON request_receipts "
                "BEGIN SELECT RAISE(ABORT, 'publication_boundary'); END",
                "AFTER INSERT ON request_receipts "
                "BEGIN INSERT INTO deferred_guard VALUES ('absent-dataset'); END",
            ]
            for index, boundary in enumerate(boundaries):
                with self.subTest(boundary=index, reopen=reopen):
                    before = tuple(corpus.connection.execute(
                        "SELECT COUNT(*) FROM " + table).fetchone()[0]
                        for table in ("datasets", "dataset_rows", "request_receipts"))
                    corpus.connection.execute("CREATE TRIGGER reject_candidate " + boundary)
                    request_id = "retry-" + str(index)
                    with self.assertRaises(sqlite3.IntegrityError) as caught:
                        corpus.build_raw(request_id, document, annotations)
                    if index < 4:
                        self.assertIn("publication_boundary", str(caught.exception))
                    else:
                        self.assertIn("FOREIGN KEY", str(caught.exception))
                    self.assertFalse(corpus.connection.in_transaction)
                    if reopen:
                        corpus.close()
                        corpus = Corpus(path)
                    after = tuple(corpus.connection.execute(
                        "SELECT COUNT(*) FROM " + table).fetchone()[0]
                        for table in ("datasets", "dataset_rows", "request_receipts"))
                    self.assertEqual(after, before)
                    self.assertEqual(corpus.read(original_id), original)
                    self.assertIsNone(corpus.connection.execute(
                        "SELECT dataset_id FROM request_receipts WHERE request_id=?",
                        (request_id,)).fetchone())
                    self.assertEqual(corpus.connection.execute(
                        "SELECT COUNT(*) FROM deferred_guard").fetchone()[0], 0)
                    corpus.connection.execute("DROP TRIGGER reject_candidate")
                    retry_id = corpus.build_raw(request_id, document, annotations)
                    self.assertEqual(corpus.build_raw(request_id, document, annotations), retry_id)
                    self.assertEqual(corpus.read(retry_id)["rows"], original["rows"])
                    expected = (before[0] + 1, before[1] + 2, before[2] + 1)
                    self.assertEqual(tuple(corpus.connection.execute(
                        "SELECT COUNT(*) FROM " + table).fetchone()[0]
                        for table in ("datasets", "dataset_rows", "request_receipts")), expected)
        finally:
            corpus.close()

    def test_atomic_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            self._exercise(str(Path(directory) / "corpus.sqlite"), True)

    def test_in_memory_failure_matrix(self):
        self._exercise(":memory:", False)
