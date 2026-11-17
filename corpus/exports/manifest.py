from copy import deepcopy
from hashlib import sha256


def jsonl_sha256(jsonl):
    return sha256(jsonl.encode("utf-8")).hexdigest()


def build_manifest(snapshot, jsonl):
    if snapshot["kind"] == "nfc_v1":
        row_count = 1
    else:
        row_count = len(snapshot["rows"])
    return {
        "dataset_id": snapshot["dataset_id"], "kind": snapshot["kind"],
        "inputs": deepcopy(snapshot["inputs"]),
        "row_count": row_count,
        "content_sha256": snapshot["content_sha256"],
        "jsonl_sha256": jsonl_sha256(jsonl),
    }
