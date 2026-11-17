from dataclasses import dataclass
from hashlib import sha256
import json
from .integrity import canonical_payload_bytes


def validate_request_id(value):
    if type(value) is not str or not value:
        raise ValueError("request_id must be a nonempty string")
    canonical_payload_bytes(value)
    return value


@dataclass(frozen=True)
class RequestReceipt:
    request_id: str
    identity_json: str
    fingerprint: str
    dataset_id: str


def make_request_identity(payload):
    return json.loads(canonical_payload_bytes(
        {"kind": payload["kind"], "inputs": payload["inputs"]}))


def request_fingerprint(identity):
    return sha256(canonical_payload_bytes(identity)).hexdigest()


def check_replay(receipt, identity):
    if receipt is None:
        return None
    expected = canonical_payload_bytes(identity)
    stored = json.loads(receipt.identity_json)
    if request_fingerprint(stored) != receipt.fingerprint:
        raise ValueError("stored request fingerprint mismatch")
    if stored != identity or canonical_payload_bytes(stored) != expected:
        raise ValueError("request_id conflicts with a different fixed input")
    return receipt.dataset_id
