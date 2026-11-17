from .revisions import make_document_revision, validate_document_reference
from .utf8 import DecodedDocument


class DocumentStore:
    def __init__(self, connection):
        self.connection = connection

    def initialize_schema(self):
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS document_heads (
                document_id TEXT PRIMARY KEY, head INTEGER NOT NULL CHECK(head > 0)
            );
            CREATE TABLE IF NOT EXISTS document_revisions (
                document_id TEXT NOT NULL, revision INTEGER NOT NULL,
                raw BLOB NOT NULL, text TEXT NOT NULL,
                source_sha256 TEXT NOT NULL, codepoint_count INTEGER NOT NULL,
                PRIMARY KEY(document_id, revision),
                FOREIGN KEY(document_id) REFERENCES document_heads(document_id)
            );
        """)

    def append_revision(self, document_id, payload):
        connection = self.connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            row = connection.execute(
                "SELECT head FROM document_heads WHERE document_id=?",
                (document_id,)).fetchone()
            revision = 1 if row is None else row[0] + 1
            value = make_document_revision(document_id, revision, payload)
            connection.execute(
                "INSERT INTO document_heads VALUES (?, ?) "
                "ON CONFLICT(document_id) DO UPDATE SET head=excluded.head",
                (document_id, revision))
            connection.execute(
                "INSERT INTO document_revisions VALUES (?, ?, ?, ?, ?, ?)",
                (document_id, revision, payload.utf8_bytes, payload.text,
                 payload.source_sha256, payload.codepoint_count))
            connection.commit()
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
        return value

    def read_revision(self, reference):
        reference = validate_document_reference(reference)
        row = self.connection.execute(
            "SELECT raw, text, source_sha256, codepoint_count "
            "FROM document_revisions WHERE document_id=? AND revision=?",
            (reference["document_id"], reference["revision"])).fetchone()
        if row is None:
            raise KeyError((reference["document_id"], reference["revision"]))
        return make_document_revision(
            reference["document_id"], reference["revision"],
            DecodedDocument(bytes(row[0]), row[1], row[2], row[3]))

    def latest_revision(self, document_id):
        row = self.connection.execute(
            "SELECT head FROM document_heads WHERE document_id=?",
            (document_id,)).fetchone()
        if row is None:
            raise KeyError(document_id)
        return row[0]
