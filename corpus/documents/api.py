from .revisions import validate_document_id, snapshot_document_revision
from .utf8 import decode_utf8


class DocumentService:
    def __init__(self, store):
        self.store = store

    def put_document(self, document_id, utf8_bytes):
        document_id = validate_document_id(document_id)
        payload = decode_utf8(utf8_bytes)
        return self.store.append_revision(document_id, payload).revision

    def read_revision(self, reference):
        return snapshot_document_revision(self.store.read_revision(reference))

    def latest_revision(self, document_id):
        return self.store.latest_revision(validate_document_id(document_id))
