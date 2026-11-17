from .records import parse_annotation_records
from .validation import validate_annotations
from .sets import snapshot_annotation_revision
from ..documents.revisions import validate_document_id


class AnnotationService:
    def __init__(self, store, documents):
        self.store = store
        self.documents = documents

    def put_annotations(self, set_id, document_revision, annotations):
        set_id = validate_document_id(set_id)
        document = self.documents.read_revision(document_revision)
        records = parse_annotation_records(annotations)
        records = validate_annotations(records, document["codepoint_count"])
        reference = {"document_id": document["document_id"],
                     "revision": document["revision"]}
        return self.store.append_revision(set_id, reference, records).revision

    def read_revision(self, reference):
        return snapshot_annotation_revision(self.store.read_revision(reference))
