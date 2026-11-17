import json


JSONL_FIELDS = (
    "dataset_id", "document_id", "document_revision",
    "annotation_set_id", "annotation_revision", "annotation_id",
    "start", "end", "label", "text",
)


def make_export_record(snapshot, row):
    document = snapshot["inputs"]["document"]
    annotations = snapshot["inputs"]["annotations"]
    values = (
        snapshot["dataset_id"], document["document_id"], document["revision"],
        annotations["set_id"], annotations["revision"],
        row["annotation_id"], row["start"], row["end"], row["label"], row["text"],
    )
    return dict(zip(JSONL_FIELDS, values))


def encode_jsonl(snapshot):
    lines = [
        json.dumps(make_export_record(snapshot, row), ensure_ascii=False,
                   separators=(",", ":"), allow_nan=False) + "\n"
        for row in snapshot["rows"]
    ]
    return "".join(lines)
