from dataclasses import dataclass
from ..documents.revisions import validate_document_reference
from ..annotations.sets import validate_annotation_reference


@dataclass(frozen=True)
class ProcessingBinding:
    document: dict
    annotations: dict


def resolve_binding(documents, annotations, document_revision, annotation_revision):
    document_reference = validate_document_reference(document_revision)
    annotation_reference = validate_annotation_reference(annotation_revision)
    document = documents.read_revision(document_reference)
    annotation = annotations.read_revision(annotation_reference)
    if annotation["document"] != document_reference:
        raise ValueError("annotations belong to a different document revision")
    return ProcessingBinding(document, annotation)


def binding_summary(binding):
    document, annotations = binding.document, binding.annotations
    return {
        "document": {
            "document_id": document["document_id"], "revision": document["revision"],
            "source_sha256": document["source_sha256"],
            "codepoint_count": document["codepoint_count"],
        },
        "annotations": {
            "set_id": annotations["set_id"], "revision": annotations["revision"],
            "sha256": annotations["sha256"],
            "record_count": len(annotations["records"]),
        },
    }
