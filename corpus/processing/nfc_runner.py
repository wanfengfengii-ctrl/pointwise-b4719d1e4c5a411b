import json
from .bindings import binding_summary
from .text import prepare_raw_text
from .normalize import nfc_with_origins, project_spans
from ..annotations.records import parse_annotation_records


class NfcRunner:
    def __init__(self, datasets):
        self.datasets = datasets

    def run(self, request_id, binding):
        text = prepare_raw_text(binding.document)
        records = parse_annotation_records(binding.annotations["records"])
        normalized, origins = nfc_with_origins(text.text)
        annotations = []
        for record in records:
            spans = project_spans(origins, record.start, record.end)
            annotations.append({
                "annotation_id": record.id,
                "start": record.start,
                "end": record.end,
                "label": json.loads(record.label_json),
                "spans": spans,
            })
        return self.datasets.publish_nfc(
            request_id, binding_summary(binding), normalized, origins, annotations)
