import hashlib
import json
import math


def _validate_json(value, active):
    if value is None or type(value) in (bool, int, str):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("non-finite JSON number")
        return
    if type(value) not in (list, dict):
        raise ValueError("value is not lossless JSON")
    identity = id(value)
    if identity in active:
        raise ValueError("cyclic JSON value")
    active.add(identity)
    try:
        if type(value) is dict:
            if any(type(key) is not str for key in value):
                raise ValueError("JSON object keys must be strings")
            children = value.values()
        else:
            children = value
        for child in children:
            _validate_json(child, active)
    finally:
        active.remove(identity)


def canonical_payload_bytes(value):
    try:
        _validate_json(value, set())
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, UnicodeError, RecursionError, OverflowError) as error:
        raise ValueError("value cannot be encoded as canonical UTF-8 JSON") from error


def _keys(value, keys, description):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError("invalid " + description)


def _integer(value, minimum, description):
    if type(value) is not int or value < minimum:
        raise ValueError("invalid " + description)


def _string(value, description):
    if type(value) is not str or not value:
        raise ValueError("invalid " + description)


def _digest(value):
    if (type(value) is not str or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)):
        raise ValueError("invalid SHA-256 digest")


def _validate_inputs(inputs):
    _keys(inputs, ("document", "annotations"), "inputs")
    document = inputs["document"]
    annotation = inputs["annotations"]
    _keys(document, ("document_id", "revision", "source_sha256", "codepoint_count"),
          "document input")
    _keys(annotation, ("set_id", "revision", "sha256", "record_count"),
          "annotation input")
    _string(document["document_id"], "document identity")
    _integer(document["revision"], 1, "document revision")
    _integer(document["codepoint_count"], 0, "codepoint count")
    _digest(document["source_sha256"])
    _string(annotation["set_id"], "annotation identity")
    _integer(annotation["revision"], 1, "annotation revision")
    _integer(annotation["record_count"], 0, "annotation count")
    _digest(annotation["sha256"])


def make_dataset_payload(inputs, rows):
    detached = json.loads(canonical_payload_bytes(
        {"kind": "raw_v1", "inputs": inputs, "rows": rows}))
    inputs, rows = detached["inputs"], detached["rows"]
    _validate_inputs(inputs)
    if type(rows) is not list or len(rows) != inputs["annotations"]["record_count"]:
        raise ValueError("candidate must contain every annotation row")
    seen = set()
    for row in rows:
        _keys(row, ("annotation_id", "start", "end", "label", "text"), "raw row")
        if type(row["annotation_id"]) is not str or row["annotation_id"] in seen:
            raise ValueError("invalid or duplicate row annotation identity")
        seen.add(row["annotation_id"])
        _integer(row["start"], 0, "row start")
        _integer(row["end"], 1, "row end")
        if not row["start"] < row["end"] <= inputs["document"]["codepoint_count"]:
            raise ValueError("row interval out of bounds")
        if type(row["text"]) is not str or len(row["text"]) != row["end"] - row["start"]:
            raise ValueError("raw row text must retain its codepoint interval")
    return detached


def make_nfc_payload(inputs, text, origins, annotations):
    detached = json.loads(canonical_payload_bytes({
        "kind": "nfc_v1", "inputs": inputs, "text": text,
        "origins": origins, "annotations": annotations}))
    inputs = detached["inputs"]
    text, origins, annotations = (detached["text"], detached["origins"],
                                  detached["annotations"])
    _validate_inputs(inputs)
    if type(text) is not str:
        raise ValueError("nfc text must be a string")
    if type(origins) is not list or len(origins) != len(text):
        raise ValueError("nfc origins must parallel the normalized text")
    for source in origins:
        if type(source) is not list or not source:
            raise ValueError("each origin entry must be a nonempty index list")
        if any(type(index) is not int or index < 0 for index in source):
            raise ValueError("origin indices must be nonnegative integers")
        if source != sorted(set(source)):
            raise ValueError("origin indices must be ascending and unique")
        if not all(index < inputs["document"]["codepoint_count"] for index in source):
            raise ValueError("origin index outside the source document")
    if type(annotations) is not list or len(annotations) != inputs["annotations"]["record_count"]:
        raise ValueError("nfc candidate must contain every annotation")
    seen = set()
    for annotation in annotations:
        _keys(annotation, ("annotation_id", "start", "end", "label", "spans"),
              "nfc annotation")
        if type(annotation["annotation_id"]) is not str or annotation["annotation_id"] in seen:
            raise ValueError("invalid or duplicate annotation identity")
        seen.add(annotation["annotation_id"])
        _integer(annotation["start"], 0, "annotation start")
        _integer(annotation["end"], 1, "annotation end")
        if not annotation["start"] < annotation["end"] <= inputs["document"]["codepoint_count"]:
            raise ValueError("annotation interval out of bounds")
        if type(annotation["spans"]) is not list:
            raise ValueError("annotation spans must be a list")
        previous_end = -1
        for span in annotation["spans"]:
            if type(span) is not list or len(span) != 2:
                raise ValueError("span must be a [start, end] pair")
            start, end = span
            _integer(start, 0, "span start")
            _integer(end, 1, "span end")
            if not start < end <= len(text) or start <= previous_end:
                raise ValueError("span out of bounds or not ascending/maximal")
            previous_end = end
    return detached


def dataset_content_digest(payload):
    return hashlib.sha256(canonical_payload_bytes(payload)).hexdigest()


def copy_dataset_snapshot(dataset_id, payload, content_sha256):
    checked = make_dataset_payload(payload["inputs"], payload["rows"])
    if payload["kind"] != "raw_v1" or checked != payload:
        raise ValueError("unsupported or malformed stored dataset")
    if dataset_content_digest(checked) != content_sha256:
        raise ValueError("stored dataset digest mismatch")
    return {"dataset_id": dataset_id, **checked, "content_sha256": content_sha256}


def copy_nfc_snapshot(dataset_id, payload, content_sha256):
    checked = make_nfc_payload(
        payload["inputs"], payload["text"], payload["origins"],
        payload["annotations"])
    if payload["kind"] != "nfc_v1" or checked != payload:
        raise ValueError("unsupported or malformed stored dataset")
    if dataset_content_digest(checked) != content_sha256:
        raise ValueError("stored dataset digest mismatch")
    return {"dataset_id": dataset_id, **checked, "content_sha256": content_sha256}
