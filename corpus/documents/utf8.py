from dataclasses import dataclass
from hashlib import sha256


@dataclass(frozen=True)
class DecodedDocument:
    utf8_bytes: bytes
    text: str
    source_sha256: str
    codepoint_count: int


def source_sha256(raw):
    return sha256(raw).hexdigest()


def decode_utf8(raw):
    if type(raw) is not bytes:
        raise ValueError("document must be UTF-8 bytes")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError("invalid UTF-8 document") from error
    return DecodedDocument(raw, text, source_sha256(raw), len(text))
