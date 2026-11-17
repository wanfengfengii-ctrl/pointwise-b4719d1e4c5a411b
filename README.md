# Fixed-revision corpus

Python 3.11 standard library only. The library captures UTF-8 document history,
freezes ordered human annotations against an exact document revision, builds
raw training rows, and publishes immutable SQLite datasets with deterministic
JSONL and an auditable source manifest.

## Run

```sh
python3.11 -B -m unittest discover -s tests -v
python3.11 -B examples.py
```

No installation or setup is needed. The demo reads the finite sample.json,
uses a temporary database, builds overlapping annotations, updates the upstream
heads, closes and reopens the database, and verifies the old release. Tests
use memory databases or their own temporary directories and propagate failures
through unittest's nonzero exit code.

## Public API

```python
from corpus import Corpus

with Corpus("corpus.sqlite") as corpus:
    revision = corpus.put_document("note", "A\u030A😀".encode("utf-8"))
    document = {"document_id": "note", "revision": revision}
    annotation_revision = corpus.put_annotations("manual", document, [
        {"id": "base", "start": 0, "end": 1, "label": {"kind": ["letter"]}},
        {"id": "accent", "start": 1, "end": 2, "label": "accent"},
    ])
    annotations = {"set_id": "manual", "revision": annotation_revision}
    dataset_id = corpus.build_raw("release-1", document, annotations)
    snapshot = corpus.read(dataset_id)
    output = corpus.export(dataset_id)
    print(output["jsonl"], end="")
    print(output["manifest"])
```

Corpus(path=":memory:") owns one synchronous SQLite connection. close() and
the context manager close it. Reopening a file initializes only missing tables
and retains all committed history. No background workers or concurrent use of
one service instance are supported. Component APIs are available through
documents, annotations, processing, datasets and exports.

documents.read_revision(document) returns document_id, revision, utf8_bytes,
text, source_sha256 and codepoint_count. documents.latest_revision(id) returns
the current number. annotations.read_revision({"set_id": id, "revision": n})
returns set_id, revision, document, records and sha256. Revision numbers start
at 1 independently for each identity; bare revision numbers are not references.

## Capture rules

Document and annotation-set identities and request IDs are nonempty strings.
Documents require bytes and strict UTF-8. Empty documents are allowed; BOM,
CRLF, supplementary characters and combining marks are retained exactly.
Every valid submission appends a revision, including identical content.
Malformed input raises ValueError without consuming a revision number.
A missing document, annotation set or revision raises KeyError.

Annotations are a list of dictionaries with exactly id, start, end and label.
Annotation IDs are strings, unique within the revision; empty annotation IDs
are permitted. Coordinates are non-boolean integers with
0 <= start < end <= len(text), measured in Python Unicode codepoints.
Overlapping and identical intervals are allowed. Submission order is retained,
and IDs, intervals or labels never cause records to be merged. An empty list
creates a real revision bound to its specified document.

Labels are losslessly representable JSON values: null, booleans, integers,
finite floats, Unicode scalar strings, lists and dictionaries with string
keys. Tuples, non-finite numbers, cycles and unsupported objects are rejected
with ValueError. Input containers and returned nested values are detached.
All records are validated before any write transaction. A late invalid record
or duplicate ID rejects the entire submission. New annotation revisions may
bind a different document revision without changing old bindings.

## Build and publish

build_raw(request_id, document, annotations) resolves both explicit references
and requires the annotation's document_id and revision to match exactly.
A different revision or a different identity with identical content is a
ValueError. Missing input is a KeyError. Processing never substitutes a head
for an explicit revision. The text snapshot checks bytes, text, length and
source digest, then rows.py slices the Python string directly.

Each annotation produces exactly one row, in submission order:
annotation_id, start, end, label, text. The text equals the original
text[start:end]. Empty annotation sets produce readable zero-row datasets.

read(dataset_id) returns dataset_id, kind="raw_v1", inputs, rows and
content_sha256. inputs contains:
- document: document_id, revision, source_sha256, codepoint_count;
- annotations: set_id, revision, sha256, record_count.

A request's identity contains raw_v1 and both complete input records above.
Same request and same identity return the original dataset ID. Different
identity raises ValueError and leaves the old receipt intact. Identity is
compared structurally as well as by its canonical encoding; fingerprints
do not substitute for identity.

Dataset validation, receipt conflict detection, metadata, all ordered rows
and the receipt are coordinated by datasets.publication and storage.
Publication writes use one transaction and return success only after commit.
Any pre-commit storage or commit error rolls back the active transaction and
propagates. No failed request leaves a dataset or receipt. Successful datasets
store their rows and source metadata independently of upstream heads.
read returns an independent snapshot; unknown datasets raise KeyError.

## Export and checksums

export(dataset_id) returns {"jsonl": str, "manifest": dict}. It reads exactly
one persisted dataset snapshot. Every row is encoded by the JSON encoder
with ensure_ascii=False and compact separators. Field order is:
dataset_id, document_id, document_revision, annotation_set_id,
annotation_revision, annotation_id, start, end, label, text.
Rows follow annotation order; each encoded record ends in LF. Embedded
newlines and control characters are escaped. Zero rows yield an empty string.

The manifest contains dataset_id, kind, complete inputs, row_count,
content_sha256 and jsonl_sha256. The last digest covers the actual returned
UTF-8 bytes including LF terminators. Output errors propagate without writes.

All canonical content digests use UTF-8 JSON with ensure_ascii=False,
sort_keys=True, separators=(",", ":"), allow_nan=False and no trailing LF.
The annotation digest covers {"document": reference, "records": ordered_records}.
The dataset digest covers {"kind": kind, "inputs": inputs, "rows": ordered_rows};
it excludes dataset and request IDs. The source digest instead covers the
original UTF-8 bytes. String normalization is never performed.

## Code and regression map

documents/{api,revisions,utf8,storage}.py own capture and document history.
annotations/{api,records,sets,validation,storage}.py own label representation,
codepoint validation and frozen annotation history.
processing/{api,bindings,text,rows,runner}.py own fixed input resolution,
raw text snapshots and row production.
datasets/{api,catalog,publication,storage,integrity,receipts}.py own candidate
checks, immutable snapshots and atomic request publication.
exports/{api,reader,jsonl,manifest}.py own one-snapshot consumption and encoding.

tests/test_capture.py checks exact bytes/codepoints, detached reads, continuous
revisions, strict decoding and document-storage rollback.
tests/test_annotations.py checks overlapping identities and order, nested label
isolation, whole-set rejection, empty sets and annotation-storage rollback.
tests/test_processing.py checks exact revision binding, original slicing,
head independence, replay conflicts, empty datasets and fixed-seed slice audits.
tests/test_datasets.py uses real SQLite triggers at metadata, row and receipt
boundaries, plus a deferred foreign-key failure at commit; it checks rollback,
retry, uniqueness and reopening a file database.
tests/test_exports.py independently parses JSONL and recomputes both digests,
checks detached values and verifies historical results after reopening.

This version processes original character coordinates only. It provides no
Unicode normalization, character-source mapping, coordinate migration or
discontinuous annotation projection.
