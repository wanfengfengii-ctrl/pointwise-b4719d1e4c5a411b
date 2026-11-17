from dataclasses import dataclass
import json
from ..annotations.validation import validate_annotations


@dataclass(frozen=True)
class RawRow:
    annotation_id: str
    start: int
    end: int
    label_json: str
    text: str


def make_raw_rows(text, records):
    records = validate_annotations(records, text.codepoint_count)
    return tuple(
        RawRow(record.id, record.start, record.end, record.label_json,
               text.text[record.start:record.end])
        for record in records
    )


def snapshot_raw_row(row):
    return {"annotation_id": row.annotation_id,
            "start": row.start, "end": row.end,
            "label": json.loads(row.label_json), "text": row.text}
