from contextlib import contextmanager
import json
from .integrity import canonical_payload_bytes
from .receipts import RequestReceipt


class DatasetStore:
    def __init__(self, connection):
        self.connection = connection

    def initialize_schema(self):
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS datasets (
                dataset_id TEXT PRIMARY KEY, kind TEXT NOT NULL,
                inputs_json TEXT NOT NULL, row_count INTEGER NOT NULL CHECK(row_count >= 0),
                content_sha256 TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS dataset_rows (
                dataset_id TEXT NOT NULL, ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
                row_json TEXT NOT NULL,
                PRIMARY KEY(dataset_id, ordinal),
                FOREIGN KEY(dataset_id) REFERENCES datasets(dataset_id)
            );
            CREATE TABLE IF NOT EXISTS request_receipts (
                request_id TEXT PRIMARY KEY, identity_json TEXT NOT NULL,
                fingerprint TEXT NOT NULL, dataset_id TEXT NOT NULL UNIQUE,
                FOREIGN KEY(dataset_id) REFERENCES datasets(dataset_id)
            );
        """)

    @contextmanager
    def transaction(self):
        connection = self.connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            yield
            connection.commit()
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise

    def _require_transaction(self):
        if not self.connection.in_transaction:
            raise RuntimeError("publication writes require a transaction")

    def find_receipt(self, request_id):
        self._require_transaction()
        row = self.connection.execute(
            "SELECT identity_json, fingerprint, dataset_id FROM request_receipts "
            "WHERE request_id=?", (request_id,)).fetchone()
        return None if row is None else RequestReceipt(request_id, *row)

    def insert_dataset(self, dataset_id, payload, content_sha256):
        self._require_transaction()
        self.connection.execute(
            "INSERT INTO datasets VALUES (?, ?, ?, ?, ?)",
            (dataset_id, payload["kind"],
             canonical_payload_bytes(payload["inputs"]).decode("utf-8"),
             len(payload["rows"]), content_sha256))

    def insert_rows(self, dataset_id, rows):
        self._require_transaction()
        for ordinal, row in enumerate(rows):
            self.connection.execute(
                "INSERT INTO dataset_rows VALUES (?, ?, ?)",
                (dataset_id, ordinal, canonical_payload_bytes(row).decode("utf-8")))

    def insert_receipt(self, receipt):
        self._require_transaction()
        self.connection.execute(
            "INSERT INTO request_receipts VALUES (?, ?, ?, ?)",
            (receipt.request_id, receipt.identity_json,
             receipt.fingerprint, receipt.dataset_id))

    def load_published(self, dataset_id):
        if self.connection.in_transaction:
            raise RuntimeError("cannot read uncommitted publication")
        metadata = self.connection.execute(
            "SELECT kind, inputs_json, row_count, content_sha256 "
            "FROM datasets WHERE dataset_id=?", (dataset_id,)).fetchone()
        if metadata is None:
            raise KeyError(dataset_id)
        rows = self.connection.execute(
            "SELECT ordinal, row_json FROM dataset_rows "
            "WHERE dataset_id=? ORDER BY ordinal", (dataset_id,)).fetchall()
        if [row[0] for row in rows] != list(range(metadata[2])):
            raise ValueError("stored dataset is incomplete")
        payload = {"kind": metadata[0], "inputs": json.loads(metadata[1]),
                   "rows": [json.loads(row[1]) for row in rows]}
        return payload, metadata[3]
