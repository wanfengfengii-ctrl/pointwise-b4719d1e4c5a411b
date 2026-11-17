from .bindings import binding_summary
from .text import prepare_raw_text
from .rows import make_raw_rows, snapshot_raw_row
from ..annotations.records import parse_annotation_records


class RawRunner:
    def __init__(self, datasets):
        self.datasets = datasets

    def run(self, request_id, binding):
        text = prepare_raw_text(binding.document)
        records = parse_annotation_records(binding.annotations["records"])
        rows = make_raw_rows(text, records)
        return self.datasets.publish_raw(
            request_id, binding_summary(binding),
            [snapshot_raw_row(row) for row in rows])
