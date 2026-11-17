from .bindings import resolve_binding
from .runner import RawRunner
from .nfc_runner import NfcRunner
from ..datasets.receipts import validate_request_id


class ProcessingService:
    def __init__(self, documents, annotations, datasets):
        self.documents = documents
        self.annotations = annotations
        self.runner = RawRunner(datasets)
        self.nfc_runner = NfcRunner(datasets)

    def build_raw(self, request_id, document_revision, annotation_revision):
        validate_request_id(request_id)
        binding = resolve_binding(
            self.documents, self.annotations, document_revision, annotation_revision)
        return self.runner.run(request_id, binding)

    def build_nfc(self, request_id, document_revision, annotation_revision):
        validate_request_id(request_id)
        binding = resolve_binding(
            self.documents, self.annotations, document_revision, annotation_revision)
        return self.nfc_runner.run(request_id, binding)
