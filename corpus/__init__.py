"""Revision-bound raw corpus processing."""
import sqlite3
from .documents.api import DocumentService
from .documents.storage import DocumentStore
from .annotations.api import AnnotationService
from .annotations.storage import AnnotationStore
from .datasets.api import DatasetService
from .datasets.storage import DatasetStore
from .processing.api import ProcessingService
from .exports.api import ExportService


class Corpus:
    """One synchronous unit of work over one SQLite database."""

    def __init__(self, path=":memory:"):
        self.connection = sqlite3.connect(path, isolation_level=None)
        try:
            self.connection.execute("PRAGMA foreign_keys = ON")
            self.connection.execute("PRAGMA busy_timeout = 5000")
            document_store = DocumentStore(self.connection)
            document_store.initialize_schema()
            annotation_store = AnnotationStore(self.connection)
            annotation_store.initialize_schema()
            dataset_store = DatasetStore(self.connection)
            dataset_store.initialize_schema()
            self.documents = DocumentService(document_store)
            self.annotations = AnnotationService(annotation_store, self.documents)
            self.datasets = DatasetService(dataset_store)
            self.processing = ProcessingService(
                self.documents, self.annotations, self.datasets)
            self.exports = ExportService(self.datasets)
        except BaseException:
            self.connection.close()
            raise

    def put_document(self, document_id, utf8_bytes):
        return self.documents.put_document(document_id, utf8_bytes)

    def put_annotations(self, set_id, document_revision, annotations):
        return self.annotations.put_annotations(
            set_id, document_revision, annotations)

    def build_raw(self, request_id, document_revision, annotation_revision):
        return self.processing.build_raw(
            request_id, document_revision, annotation_revision)

    def build_nfc(self, request_id, document_revision, annotation_revision):
        return self.processing.build_nfc(
            request_id, document_revision, annotation_revision)

    def read(self, dataset_id):
        return self.datasets.read(dataset_id)

    def export(self, dataset_id):
        return self.exports.export(dataset_id)

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()
