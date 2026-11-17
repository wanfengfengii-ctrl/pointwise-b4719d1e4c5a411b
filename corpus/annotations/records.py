from dataclasses import dataclass
import json
from ..datasets.integrity import canonical_payload_bytes


@dataclass(frozen=True)
class AnnotationRecord:
    id: str
    start: int
    end: int
    label_json: str


def parse_annotation_records(records):
    if type(records) is not list:
        raise ValueError("annotations must be a list")
    result = []
    for record in records:
        if type(record) is not dict or set(record) != {"id", "start", "end", "label"}:
            raise ValueError("annotation requires id, start, end, label")
        if type(record["id"]) is not str:
            raise ValueError("annotation id must be a string")
        canonical_payload_bytes(record["id"])
        label_json = canonical_payload_bytes(record["label"]).decode("utf-8")
        result.append(AnnotationRecord(
            record["id"], record["start"], record["end"], label_json))
    return tuple(result)


def snapshot_annotation_record(record):
    return {"id": record.id, "start": record.start, "end": record.end,
            "label": json.loads(record.label_json)}
