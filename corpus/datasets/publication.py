import uuid
from .integrity import (
    make_dataset_payload, make_nfc_payload, dataset_content_digest,
    canonical_payload_bytes,
)
from .receipts import (
    validate_request_id, make_request_identity, request_fingerprint,
    RequestReceipt, check_replay,
)


class DatasetPublisher:
    def __init__(self, store):
        self.store = store

    def publish(self, request_id, inputs, rows):
        validate_request_id(request_id)
        payload = make_dataset_payload(inputs, rows)
        identity = make_request_identity(payload)
        digest = dataset_content_digest(payload)
        with self.store.transaction():
            existing = check_replay(self.store.find_receipt(request_id), identity)
            if existing is not None:
                dataset_id = existing
            else:
                dataset_id = uuid.uuid4().hex
                self.store.insert_dataset(dataset_id, payload, digest)
                self.store.insert_rows(dataset_id, payload["rows"])
                self.store.insert_receipt(RequestReceipt(
                    request_id, canonical_payload_bytes(identity).decode("utf-8"),
                    request_fingerprint(identity), dataset_id))
        return dataset_id

    def publish_nfc(self, request_id, inputs, text, origins, annotations):
        validate_request_id(request_id)
        payload = make_nfc_payload(inputs, text, origins, annotations)
        identity = make_request_identity(payload)
        digest = dataset_content_digest(payload)
        with self.store.transaction():
            existing = check_replay(self.store.find_receipt(request_id), identity)
            if existing is not None:
                dataset_id = existing
            else:
                dataset_id = uuid.uuid4().hex
                self.store.insert_nfc_dataset(dataset_id, payload, digest)
                self.store.insert_receipt(RequestReceipt(
                    request_id, canonical_payload_bytes(identity).decode("utf-8"),
                    request_fingerprint(identity), dataset_id))
        return dataset_id
