from dataclasses import dataclass
from .utf8 import DecodedDocument, decode_utf8


def validate_document_id(value):
    if type(value) is not str or not value:
        raise ValueError("document_id must be a nonempty string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError("document_id must be Unicode scalar text") from error
    return value


def validate_document_reference(reference):
    if type(reference) is not dict or set(reference) != {"document_id", "revision"}:
        raise ValueError("document reference requires document_id and revision")
    identity = validate_document_id(reference["document_id"])
    revision = reference["revision"]
    if type(revision) is not int or revision < 1:
        raise ValueError("revision must be a positive integer")
    return {"document_id": identity, "revision": revision}


@dataclass(frozen=True)
class DocumentRevision:
    document_id: str
    revision: int
    payload: DecodedDocument


def make_document_revision(document_id, revision, payload):
    reference = validate_document_reference(
        {"document_id": document_id, "revision": revision})
    if not isinstance(payload, DecodedDocument):
        raise ValueError("decoded document required")
    checked = decode_utf8(payload.utf8_bytes)
    if checked != payload:
        raise ValueError("document payload is inconsistent")
    return DocumentRevision(reference["document_id"], revision, checked)


def snapshot_document_revision(value):
    return {
        "document_id": value.document_id,
        "revision": value.revision,
        "utf8_bytes": value.payload.utf8_bytes,
        "text": value.payload.text,
        "source_sha256": value.payload.source_sha256,
        "codepoint_count": value.payload.codepoint_count,
    }
