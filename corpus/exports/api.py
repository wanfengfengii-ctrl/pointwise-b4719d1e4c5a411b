from .reader import ExportReader
from .jsonl import encode_jsonl
from .manifest import build_manifest


class ExportService:
    def __init__(self, datasets):
        self.reader = ExportReader(datasets)

    def export(self, dataset_id):
        snapshot = self.reader.load(dataset_id)
        jsonl = encode_jsonl(snapshot)
        return {"jsonl": jsonl, "manifest": build_manifest(snapshot, jsonl)}
