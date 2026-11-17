from dataclasses import dataclass
from hashlib import sha256
from .records import snapshot_annotation_record
from ..documents.revisions import validate_document_reference, validate_document_id
from ..datasets.integrity import canonical_payload_bytes


def validate_annotation_reference(reference):
    if type(reference) is not dict or set(reference) != {"set_id", "revision"}:
        raise ValueError("annotation reference requires set_id and revision")
    set_id = validate_document_id(reference["set_id"])
    revision = reference["revision"]
    if type(revision) is not int or revision < 1:
        raise ValueError("annotation revision must be a positive integer")
    return {"set_id": set_id, "revision": revision}


@dataclass(frozen=True)
class AnnotationRevision:
    set_id: str
    revision: int
    document_id: str
    document_revision: int
    records: tuple
    sha256: str


def annotation_set_digest(document, records):
    payload = {"document": validate_document_reference(document),
               "records": [snapshot_annotation_record(record) for record in records]}
    return sha256(canonical_payload_bytes(payload)).hexdigest()


def make_annotation_revision(set_id, revision, document, records):
    validate_annotation_reference({"set_id": set_id, "revision": revision})
    document = validate_document_reference(document)
    records = tuple(records)
    return AnnotationRevision(
        set_id, revision, document["document_id"], document["revision"],
        records, annotation_set_digest(document, records))


def snapshot_annotation_revision(value):
    return {
        "set_id": value.set_id, "revision": value.revision,
        "document": {"document_id": value.document_id,
                     "revision": value.document_revision},
        "records": [snapshot_annotation_record(record) for record in value.records],
        "sha256": value.sha256,
    }
