import json
from .records import parse_annotation_records, snapshot_annotation_record
from .sets import make_annotation_revision, validate_annotation_reference
from ..datasets.integrity import canonical_payload_bytes


class AnnotationStore:
    def __init__(self, connection):
        self.connection = connection

    def initialize_schema(self):
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS annotation_heads (
                set_id TEXT PRIMARY KEY, head INTEGER NOT NULL CHECK(head > 0)
            );
            CREATE TABLE IF NOT EXISTS annotation_revisions (
                set_id TEXT NOT NULL, revision INTEGER NOT NULL,
                document_id TEXT NOT NULL, document_revision INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                PRIMARY KEY(set_id, revision),
                FOREIGN KEY(set_id) REFERENCES annotation_heads(set_id),
                FOREIGN KEY(document_id, document_revision)
                    REFERENCES document_revisions(document_id, revision)
            );
            CREATE TABLE IF NOT EXISTS annotation_records (
                set_id TEXT NOT NULL, revision INTEGER NOT NULL,
                ordinal INTEGER NOT NULL CHECK(ordinal >= 0), record_json TEXT NOT NULL,
                PRIMARY KEY(set_id, revision, ordinal),
                FOREIGN KEY(set_id, revision)
                    REFERENCES annotation_revisions(set_id, revision)
            );
        """)

    def append_revision(self, set_id, document, records):
        connection = self.connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            row = connection.execute(
                "SELECT head FROM annotation_heads WHERE set_id=?", (set_id,)).fetchone()
            revision = 1 if row is None else row[0] + 1
            value = make_annotation_revision(set_id, revision, document, records)
            connection.execute(
                "INSERT INTO annotation_heads VALUES (?, ?) "
                "ON CONFLICT(set_id) DO UPDATE SET head=excluded.head",
                (set_id, revision))
            connection.execute(
                "INSERT INTO annotation_revisions VALUES (?, ?, ?, ?, ?)",
                (set_id, revision, value.document_id,
                 value.document_revision, value.sha256))
            connection.executemany(
                "INSERT INTO annotation_records VALUES (?, ?, ?, ?)",
                [(set_id, revision, ordinal,
                  canonical_payload_bytes(snapshot_annotation_record(record)).decode("utf-8"))
                 for ordinal, record in enumerate(value.records)])
            connection.commit()
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
        return value

    def read_revision(self, reference):
        reference = validate_annotation_reference(reference)
        key = (reference["set_id"], reference["revision"])
        row = self.connection.execute(
            "SELECT document_id, document_revision, sha256 "
            "FROM annotation_revisions WHERE set_id=? AND revision=?", key).fetchone()
        if row is None:
            raise KeyError(key)
        stored = self.connection.execute(
            "SELECT record_json FROM annotation_records "
            "WHERE set_id=? AND revision=? ORDER BY ordinal", key).fetchall()
        records = parse_annotation_records([json.loads(item[0]) for item in stored])
        value = make_annotation_revision(
            *key, {"document_id": row[0], "revision": row[1]}, records)
        if value.sha256 != row[2]:
            raise ValueError("stored annotation digest mismatch")
        return value
