class ExportReader:
    def __init__(self, datasets):
        self.datasets = datasets

    def load(self, dataset_id):
        snapshot = self.datasets.read(dataset_id)
        if snapshot["kind"] != "raw_v1":
            raise ValueError("unsupported export dataset kind")
        return snapshot
