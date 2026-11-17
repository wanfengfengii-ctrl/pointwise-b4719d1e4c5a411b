"""Finite NFC contract fixtures; no implementation of provenance inference."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unicodedata
from corpus import Corpus

# source, NFC text, origins, (original start, end, expected spans)
CASES = [
    ("A\u030a", "\u00c5", [[0, 1]],
     [(0, 1, [[0, 1]]), (1, 2, [[0, 1]])]),
    ("a\u0315\u0300", "\u00e0\u0315", [[0, 2], [1]],
     [(0, 2, [[0, 2]]), (1, 2, [[1, 2]]), (2, 3, [[0, 1]])]),
    ("q\u0315\u0300", "q\u0300\u0315", [[0], [2], [1]],
     [(0, 2, [[0, 1], [2, 3]]), (1, 3, [[1, 3]])]),
    ("A\u0305\u030a", "A\u0305\u030a", [[0], [1], [2]],
     [(0, 3, [[0, 3]]), (2, 3, [[2, 3]])]),
    ("\u0344", "\u0308\u0301", [[0], [0]], [(0, 1, [[0, 2]])]),
    ("\u1100\u1161\u11a8", "\uac01", [[0, 1, 2]],
     [(0, 1, [[0, 1]]), (1, 3, [[0, 1]])]),
    ("A\u030a\u030a", "\u00c5\u030a", [[0, 1], [2]],
     [(0, 1, [[0, 1]]), (1, 2, [[0, 1]]), (2, 3, [[1, 2]])]),
    ("\u00c5\u0323\u030a", "\u1ea0\u030a\u030a", [[0, 1], [0], [2]],
     [(0, 1, [[0, 2]]), (2, 3, [[2, 3]])]),
    ("", "", [], []),
    ("😀\r\n", "😀\r\n", [[0], [1], [2]], []),
]

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")

def expected_annotations(case):
    return [
        {"annotation_id": str(i), "start": a, "end": b,
         "label": {"tags": [i, "人工\n复核"]}, "spans": spans}
        for i, (a, b, spans) in enumerate(case[3])
    ]

def prepare(corpus, case, identity):
    revision = corpus.put_document(identity, case[0].encode("utf-8"))
    document = {"document_id": identity, "revision": revision}
    records = [
        {"id": r["annotation_id"], "start": r["start"], "end": r["end"],
         "label": r["label"]}
        for r in expected_annotations(case)
    ]
    revision = corpus.put_annotations(identity, document, records)
    return document, {"set_id": identity, "revision": revision}

def audit(corpus, dataset_id, case):
    saved = corpus.read(dataset_id)
    assert set(saved) == {"dataset_id", "kind", "inputs", "text", "origins",
                          "annotations", "content_sha256"}
    assert saved["dataset_id"] == dataset_id
    assert saved["kind"] == "nfc_v1"
    assert saved["text"] == case[1]
    assert saved["origins"] == case[2]
    assert saved["annotations"] == expected_annotations(case)
    assert corpus.datasets.read(dataset_id) == saved
    fields = ("kind", "inputs", "text", "origins", "annotations")
    digest = hashlib.sha256(canonical({k: saved[k] for k in fields})).hexdigest()
    assert saved["content_sha256"] == digest
    exported = corpus.export(dataset_id)
    assert corpus.exports.export(dataset_id) == exported
    record = {k: saved[k] for k in ("dataset_id",) + fields}
    jsonl = exported["jsonl"]
    decoded = json.loads(jsonl)
    assert decoded == record
    assert list(decoded) == list(record)
    assert jsonl == json.dumps(decoded, ensure_ascii=False,
                              separators=(",", ":"), allow_nan=False) + "\n"
    assert exported["manifest"] == {
        "dataset_id": dataset_id, "kind": "nfc_v1", "inputs": saved["inputs"],
        "row_count": 1, "content_sha256": digest,
        "jsonl_sha256": hashlib.sha256(jsonl.encode("utf-8")).hexdigest(),
    }
    return saved, exported

def must_raise(error_type, action):
    try:
        action()
    except error_type:
        return
    raise AssertionError("expected " + error_type.__name__)

def exercise_memory():
    with Corpus() as corpus:
        for i, case in enumerate(CASES):
            document, annotations = prepare(corpus, case, "case-" + str(i))
            request = "nfc-" + str(i)
            dataset_id = corpus.build_nfc(request, document, annotations)
            saved, exported = audit(corpus, dataset_id, case)
            raw_id = corpus.build_raw("raw-" + str(i), document, annotations)
            assert corpus.read(raw_id)["inputs"] == saved["inputs"]
            assert corpus.processing.build_nfc(request, document, annotations) == dataset_id
            must_raise(ValueError, lambda: corpus.build_raw(request, document, annotations))
            must_raise(ValueError, lambda: corpus.build_nfc("raw-" + str(i), document, annotations))
            changed = corpus.read(dataset_id)
            changed["origins"].append([999])
            changed["inputs"]["document"]["revision"] = 999
            if changed["annotations"]:
                changed["annotations"][0]["label"]["tags"].clear()
                changed["annotations"][0]["spans"].clear()
            assert corpus.read(dataset_id) == saved
            assert corpus.export(dataset_id) == exported
        case = CASES[2]
        document, annotations = prepare(corpus, case, "history")
        raw_id = corpus.build_raw("history-raw", document, annotations)
        original_raw = corpus.read(raw_id), corpus.export(raw_id)
        dataset_id = corpus.build_nfc("history-nfc", document, annotations)
        before = audit(corpus, dataset_id, case)
        corpus.put_document("history", b"replacement")
        newer = {"document_id": "history", "revision": 2}
        ann_revision = corpus.put_annotations("history", newer, [])
        new_annotations = {"set_id": "history", "revision": ann_revision}
        must_raise(ValueError, lambda: corpus.build_nfc("mismatch", newer, annotations))
        must_raise(KeyError, lambda: corpus.build_nfc(
            "missing", {"document_id": "history", "revision": 99}, annotations))
        must_raise(ValueError, lambda: corpus.build_nfc("history-nfc", newer, new_annotations))
        corpus.connection.execute("PRAGMA query_only=ON")
        try:
            must_raise(sqlite3.OperationalError,
                       lambda: corpus.build_nfc("retry-after-write-error", document, annotations))
        finally:
            corpus.connection.execute("PRAGMA query_only=OFF")
        assert not corpus.connection.in_transaction
        retry_id = corpus.build_nfc("retry-after-write-error", document, annotations)
        audit(corpus, retry_id, case)
        assert corpus.build_nfc("retry-after-write-error", document, annotations) == retry_id
        assert audit(corpus, dataset_id, case) == before
        assert (corpus.read(raw_id), corpus.export(raw_id)) == original_raw

def exercise_reopen(show=False):
    with tempfile.TemporaryDirectory() as directory:
        path = str(Path(directory) / "corpus.sqlite")
        releases = []
        with Corpus(path) as corpus:
            for index in (0, 2):
                case = CASES[index]
                identity = "note-" + str(index)
                document, annotations = prepare(corpus, case, identity)
                raw_id = corpus.build_raw("raw-" + identity, document, annotations)
                raw = corpus.read(raw_id), corpus.export(raw_id)
                request = "nfc-" + identity
                dataset_id = corpus.build_nfc(request, document, annotations)
                before = audit(corpus, dataset_id, case)
                releases.append((case, document, annotations, request,
                                 dataset_id, before, raw_id, raw))
                corpus.put_document(identity, b"new head")
                corpus.put_annotations(
                    identity, {"document_id": identity, "revision": 2}, [])
        with Corpus(path) as corpus:
            for (case, document, annotations, request,
                 dataset_id, before, raw_id, raw) in releases:
                assert audit(corpus, dataset_id, case) == before
                assert corpus.build_nfc(request, document, annotations) == dataset_id
                assert (corpus.read(raw_id), corpus.export(raw_id)) == raw
                if show:
                    print(before[1]["jsonl"], end="")
                    print(json.dumps(before[1]["manifest"], ensure_ascii=False, sort_keys=True))

def main():
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    for name in ("fixtures", "check", "demo"):
        modes.add_argument("--" + name, dest="mode", action="store_const", const=name)
    mode = "--" + parser.parse_args().mode
    if mode == "--fixtures":
        for case in CASES:
            assert unicodedata.normalize("NFC", case[0]) == case[1]
            assert len(case[1]) == len(case[2])
            for origins in case[2]:
                assert origins and origins == sorted(set(origins))
                assert all(0 <= p < len(case[0]) for p in origins)
        print(json.dumps({"fixture_count": len(CASES),
                          "unicode_version": unicodedata.unidata_version}, sort_keys=True))
    elif mode == "--check":
        exercise_memory()
        exercise_reopen()
        print("NFC joint checks passed")
    else:
        exercise_reopen(show=True)

if __name__ == "__main__":
    main()
