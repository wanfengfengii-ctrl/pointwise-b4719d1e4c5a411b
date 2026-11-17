import json
from pathlib import Path
import tempfile
from corpus import Corpus


def main():
    sample = json.loads(Path(__file__).with_name("sample.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as directory:
        path = str(Path(directory) / "corpus.sqlite")
        with Corpus(path) as corpus:
            revision = corpus.put_document(sample["document_id"], sample["text"].encode("utf-8"))
            document = {"document_id": sample["document_id"], "revision": revision}
            annotation_revision = corpus.put_annotations(
                sample["set_id"], document, sample["annotations"])
            annotation = {"set_id": sample["set_id"], "revision": annotation_revision}
            dataset_id = corpus.build_raw("field-note-release", document, annotation)
            saved, exported = corpus.read(dataset_id), corpus.export(dataset_id)
            assert [row["text"] for row in saved["rows"]] == [
                sample["text"][row["start"]:row["end"]] for row in sample["annotations"]]
            assert corpus.build_raw("field-note-release", document, annotation) == dataset_id
            corpus.put_document(sample["document_id"], b"corrected source")
            corpus.put_annotations(
                sample["set_id"], {"document_id": sample["document_id"], "revision": 2}, [])
        with Corpus(path) as corpus:
            assert corpus.read(dataset_id) == saved
            assert corpus.export(dataset_id) == exported
            assert corpus.build_raw("field-note-release", document, annotation) == dataset_id
            print(json.dumps(exported["manifest"], ensure_ascii=False, sort_keys=True))
            print(exported["jsonl"], end="")


if __name__ == "__main__":
    main()
