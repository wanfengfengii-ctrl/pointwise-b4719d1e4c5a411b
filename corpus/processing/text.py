from dataclasses import dataclass
from ..documents.utf8 import decode_utf8


@dataclass(frozen=True)
class RawText:
    text: str
    codepoint_count: int
    source_sha256: str


def prepare_raw_text(document):
    payload = decode_utf8(document["utf8_bytes"])
    if (payload.text != document["text"]
            or payload.codepoint_count != document["codepoint_count"]
            or payload.source_sha256 != document["source_sha256"]):
        raise ValueError("inconsistent fixed document snapshot")
    return RawText(payload.text, payload.codepoint_count, payload.source_sha256)
