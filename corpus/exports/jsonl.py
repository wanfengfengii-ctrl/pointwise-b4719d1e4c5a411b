import json


JSONL_FIELDS = (
    "dataset_id", "document_id", "document_revision",
    "annotation_set_id", "annotation_revision", "annotation_id",
    "start", "end", "label", "text",
)

NFC_FIELDS = ("dataset_id", "kind", "inputs", "text", "origins", "annotations")


def make_export_record(snapshot, row):
    document = snapshot["inputs"]["document"]
    annotations = snapshot["inputs"]["annotations"]
    values = (
        snapshot["dataset_id"], document["document_id"], document["revision"],
        annotations["set_id"], annotations["revision"],
        row["annotation_id"], row["start"], row["end"], row["label"], row["text"],
    )
    return dict(zip(JSONL_FIELDS, values))


def make_nfc_export_record(snapshot):
    return {field: snapshot[field] for field in NFC_FIELDS}


def encode_jsonl(snapshot):
    if snapshot["kind"] == "nfc_v1":
        return json.dumps(make_nfc_export_record(snapshot), ensure_ascii=False,
                          separators=(",", ":"), allow_nan=False) + "\n"
    lines = [
        json.dumps(make_export_record(snapshot, row), ensure_ascii=False,
                   separators=(",", ":"), allow_nan=False) + "\n"
        for row in snapshot["rows"]
    ]
    return "".join(lines)
