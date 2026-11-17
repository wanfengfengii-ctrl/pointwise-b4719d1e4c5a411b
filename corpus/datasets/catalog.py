from .integrity import copy_dataset_snapshot, copy_nfc_snapshot


class DatasetCatalog:
    def __init__(self, store):
        self.store = store

    def read_published(self, dataset_id):
        if type(dataset_id) is not str or not dataset_id:
            raise ValueError("dataset_id must be a nonempty string")
        payload, digest = self.store.load_published(dataset_id)
        if payload["kind"] == "nfc_v1":
            return copy_nfc_snapshot(dataset_id, payload, digest)
        return copy_dataset_snapshot(dataset_id, payload, digest)
