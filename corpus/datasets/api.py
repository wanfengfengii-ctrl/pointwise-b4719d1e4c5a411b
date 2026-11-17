from .catalog import DatasetCatalog
from .publication import DatasetPublisher


class DatasetService:
    def __init__(self, store):
        self.store = store
        self.publisher = DatasetPublisher(store)
        self.catalog = DatasetCatalog(store)

    def publish_raw(self, request_id, inputs, rows):
        return self.publisher.publish(request_id, inputs, rows)

    def read(self, dataset_id):
        return self.catalog.read_published(dataset_id)
