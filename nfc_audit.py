"""Independent NFC provenance audit.

This auditor deliberately does not import any production normalization
code.  Its reference transform re-derives canonical decomposition,
ordering and composition directly from the interpreter's unicodedata
tables with different data structures (named token records, separate
NFD/order/compose passes) than corpus/processing/normalize.py, then
cross-checks the published corpus results.  It exits nonzero on the
first failed invariant.

Checks:
  1. static nfc_examples fixtures (repeated marks, blocking, exclusion,
     Hangul, empty document);
  2. whole-document transform equality with unicodedata.normalize("NFC");
  3. origins are nonempty, ascending, unique, in-bounds and partition the
     source positions;
  4. recomposition/exclusion behavior on Devanagari and Tibetan pairs and
     Hangul block boundaries;
  5. annotation projection: intersection selection, maximal spans,
     submission order/ID/label retention and shared characters;
  6. full publication, checksums, export framing and replay/conflict rules;
  7. failed writes leave no dataset or receipt and remain retryable;
  8. upstream replacement and file reopen never change old releases.

Run:  python3.11 -B nfc_audit.py
"""
import hashlib
import json
import random
import sqlite3
import tempfile
import unicodedata
from pathlib import Path

from corpus import Corpus
from nfc_examples import CASES, canonical, expected_annotations, prepare

L0, V0, T0 = 0x1100, 0x1161, 0x11A7
L_N, V_N, T_N = 19, 21, 28
S0, S_N = 0xAC00, L_N * V_N * T_N
N = V_N * T_N


def _decompose_one(cp):
    """Independent arithmetic/table canonical decomposition (one level)."""
    offset = cp - S0
    if 0 <= offset < S_N:
        pieces = [L0 + offset // N, V0 + (offset % N) // T_N]
        if offset % T_N:
            pieces.append(T0 + offset % T_N)
        return pieces
    field = unicodedata.decomposition(chr(cp))
    if field and not field.startswith("<"):
        return [int(token, 16) for token in field.split()]
    return [cp]


def _recursive_nfd(cp):
    out = []
    stack = [cp]
    while stack:
        token = stack.pop()
        parts = _decompose_one(token)
        if parts == [token]:
            out.append(token)
        else:
            stack.extend(reversed(parts))
    return out


def _reference_transform(text):
    """Independent NFC + provenance implementation using record tokens."""
    tokens = []
    for position, char in enumerate(text):
        for piece in _recursive_nfd(ord(char)):
            tokens.append({"code": piece, "src": [position]})

    def swap_sort(items):
        again = True
        while again:
            again = False
            for i in range(len(items) - 1):
                c1 = unicodedata.combining(chr(items[i]["code"]))
                c2 = unicodedata.combining(chr(items[i + 1]["code"]))
                if c2 and c1 > c2:  # starters (incl. Hangul jamo) never cross
                    items[i], items[i + 1] = items[i + 1], items[i]
                    again = True

    swap_sort(tokens)
    primary, secondary = _reference_pair_tables()

    def combine(a, b, adjacent):
        if adjacent:
            if L0 <= a < L0 + L_N and V0 <= b < V0 + V_N:
                return S0 + ((a - L0) * V_N + (b - V0)) * T_N
            if S0 <= a < S0 + S_N and (a - S0) % T_N == 0 and T0 < b < T0 + T_N:
                return a + (b - T0)
        hit = primary.get((a, b))
        if hit is None and unicodedata.combining(chr(a)) != 0:
            hit = secondary.get((a, b))
        return hit

    anchor = 0
    cursor = 1
    while cursor < len(tokens):
        a = tokens[anchor]["code"]
        b = tokens[cursor]["code"]
        ca = unicodedata.combining(chr(a))
        cb = unicodedata.combining(chr(b))
        blocked = False
        if cursor > anchor + 1:
            cp = unicodedata.combining(chr(tokens[cursor - 1]["code"]))
            blocked = (cp >= cb) if ca != 0 else (cp != 0 and cp >= cb)
        if not blocked:
            merged = combine(a, b, cursor == anchor + 1)
            if merged is not None:
                tokens[anchor]["code"] = merged
                tokens[anchor]["src"] = sorted(
                    set(tokens[anchor]["src"]) | set(tokens[cursor]["src"]))
                del tokens[cursor]
                continue
        if cb == 0:
            anchor = cursor
        cursor += 1
    return "".join(chr(t["code"]) for t in tokens), [t["src"] for t in tokens]


def _reference_pair_tables():
    primary, secondary = {}, {}
    for codepoint in range(0x110000):
        field = unicodedata.decomposition(chr(codepoint))
        if not field or field.startswith("<") or len(field.split()) != 2:
            continue
        x, y = (int(token, 16) for token in field.split())
        if unicodedata.normalize("NFC", chr(x) + chr(y)) != chr(codepoint):
            continue  # composition exclusion honored
        bucket = primary if unicodedata.combining(chr(x)) == 0 else secondary
        bucket[(x, y)] = codepoint
    return primary, secondary


def _spans_from_origins(origins, start, end):
    chosen = [j for j, src in enumerate(origins)
              if any(start <= index < end for index in src)]
    spans = []
    for position in chosen:
        if spans and spans[-1][1] == position:
            spans[-1][1] = position + 1
        else:
            spans.append([position, position + 1])
    return spans


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def audit_fixtures():
    for source, text, origins, annotations in CASES:
        check(unicodedata.normalize("NFC", source) == text, "fixture NFC mismatch")
        produced_text, produced_origins = _reference_transform(source)
        check(produced_text == text, "reference text mismatch for " + repr(source))
        check(produced_origins == origins, "reference origins mismatch for " + repr(source))
        check(len(produced_origins) == len(produced_text), "origins length")
        covered = sorted({i for src in produced_origins for i in src})
        check(covered == list(range(len(source))), "origin partition")
        for src in produced_origins:
            check(src and src == sorted(set(src)), "origin shape")
        for start, end, spans in annotations:
            check(_spans_from_origins(origins, start, end) == spans,
                  "fixture projection mismatch")


def audit_randomized():
    rng = random.Random(20261117)
    alphabet = [
        0x41, 0x61, 0x71, 0x300, 0x301, 0x308, 0x30A, 0x315, 0x305, 0x323,
        0x344, 0x390, 0xC5, 0x1EA0, 0x1100, 0x1161, 0x11A8, 0x1F600, 0x0D,
        0x0A, 0x200D, 0x915, 0x93C, 0x3B9, 0x3CA, 0xF71, 0xF72,
    ]
    for trial in range(1500):
        count = rng.randrange(0, 14)
        source = "".join(chr(rng.choice(alphabet)) for _ in range(count))
        text, origins = _reference_transform(source)
        check(text == unicodedata.normalize("NFC", source), "randomized NFC oracle")
        check(len(text) == len(origins), "randomized origins length")
        if count:
            check(sorted({i for src in origins for i in src}) == list(range(count)),
                  "randomized origin partition")
        if count:
            start = rng.randrange(count)
            end = rng.randrange(start + 1, count + 1)
            spans = _spans_from_origins(origins, start, end)
            expected_positions = [
                j for j, src in enumerate(origins)
                if any(start <= i < end for i in src)]
            check([j for lo, hi in spans for j in range(lo, hi)] == expected_positions,
                  "randomized projection coverage")
            check(all(spans[k][1] < spans[k + 1][0] for k in range(len(spans) - 1)),
                  "randomized span gaps")


def audit_special_rules():
    # Composition exclusion: Devanagari ka + nukta never becomes 0958.
    text, origins = _reference_transform("क़")
    check(text == unicodedata.normalize("NFC", "क़")
          == "क़", "exclusion: Devanagari")
    # Blocking: A + overline(ccc 230) + ring(ccc 230) must not recompose.
    text, origins = _reference_transform("Å̅̊")
    check(text == "Å̅̊" and origins == [[0], [1], [2]], "blocked composition")
    # Hangul: full syllable composition and a T jamo blocked behind a mark.
    check(_reference_transform("각")[0] == "각", "Hangul LV+T composition")
    blocked_source = chr(0x0344) + chr(0x11A8)
    text, origins = _reference_transform(blocked_source)
    expected_text = unicodedata.normalize("NFC", blocked_source)
    # The combining marks stay ahead of the ccc=0 T jamo; the jamo is
    # never reordered past them and nothing recomposes.
    check(text == expected_text and text == chr(0x0308) + chr(0x0301) + chr(0x11A8),
          "Hangul T jamo blocking order")
    check(origins == [[0], [0], [1]], "Hangul blocked origins")
    # Secondary composite path stays equivalent to the environment table.
    check(_reference_transform("ΐ")[0] == unicodedata.normalize("NFC", "ΐ"),
          "secondary composite equivalence")


def audit_publication():
    with Corpus() as corpus:
        for index, case in enumerate(CASES):
            document, annotations = prepare(corpus, case, "audit-" + str(index))
            request = "audit-request-" + str(index)
            dataset_id = corpus.build_nfc(request, document, annotations)
            saved = corpus.read(dataset_id)
            check(set(saved) == {"dataset_id", "kind", "inputs", "text", "origins",
                                 "annotations", "content_sha256"}, "read shape")
            text, origins = _reference_transform(case[0])
            check(saved["text"] == text and saved["origins"] == origins,
                  "published provenance")
            check(saved["annotations"] == expected_annotations(case),
                  "published projections")
            digest = hashlib.sha256(canonical({
                "kind": "nfc_v1", "inputs": saved["inputs"], "text": saved["text"],
                "origins": saved["origins"], "annotations": saved["annotations"],
            })).hexdigest()
            check(saved["content_sha256"] == digest, "content digest")
            exported = corpus.export(dataset_id)
            record = json.loads(exported["jsonl"])
            check(list(record) == ["dataset_id", "kind", "inputs", "text",
                                   "origins", "annotations"], "jsonl field order")
            check(exported["jsonl"].endswith("\n") and
                  exported["jsonl"].count("\n") == 1, "jsonl framing")
            check(exported["manifest"] == {
                "dataset_id": dataset_id, "kind": "nfc_v1",
                "inputs": saved["inputs"], "row_count": 1,
                "content_sha256": digest,
                "jsonl_sha256": hashlib.sha256(
                    exported["jsonl"].encode("utf-8")).hexdigest(),
            }, "manifest")
            check(corpus.build_nfc(request, document, annotations) == dataset_id,
                  "replay returns same id")
            try:
                corpus.build_raw(request, document, annotations)
            except ValueError:
                pass
            else:
                raise AssertionError("kind conflict must raise")
            # Isolation of returned containers.
            saved["origins"].append([1000])
            check(corpus.read(dataset_id)["origins"] == origins, "detached read")
        # Failure leaves no artifact; retry then succeeds.
        case = CASES[2]
        document, annotations = prepare(corpus, case, "failure")
        corpus.connection.execute("PRAGMA query_only=ON")
        try:
            try:
                corpus.build_nfc("failed-once", document, annotations)
            except sqlite3.OperationalError:
                pass
            else:
                raise AssertionError("write failure must propagate")
        finally:
            corpus.connection.execute("PRAGMA query_only=OFF")
        check(not corpus.connection.in_transaction, "transaction rolled back")
        check(corpus.connection.execute(
            "SELECT COUNT(*) FROM request_receipts WHERE request_id='failed-once'"
        ).fetchone()[0] == 0, "no receipt after failure")
        retry_id = corpus.build_nfc("failed-once", document, annotations)
        check(corpus.build_nfc("failed-once", document, annotations) == retry_id,
              "retry after failure")


def audit_reopen():
    case = CASES[7]
    with tempfile.TemporaryDirectory() as directory:
        path = str(Path(directory) / "audit.sqlite")
        with Corpus(path) as corpus:
            document, annotations = prepare(corpus, case, "reopen")
            dataset_id = corpus.build_nfc("reopen-request", document, annotations)
            before = (corpus.read(dataset_id), corpus.export(dataset_id))
            corpus.put_document("reopen", b"new upstream head")
            corpus.put_annotations(
                "reopen", {"document_id": "reopen", "revision": 2}, [])
        with Corpus(path) as corpus:
            check((corpus.read(dataset_id), corpus.export(dataset_id)) == before,
                  "reopen preserves release")
            check(corpus.build_nfc("reopen-request", document, annotations)
                  == dataset_id, "replay after reopen")


def main():
    audit_fixtures()
    audit_randomized()
    audit_special_rules()
    audit_publication()
    audit_reopen()
    print(json.dumps({
        "status": "nfc provenance audit passed",
        "unicode_version": unicodedata.unidata_version,
        "fixture_cases": len(CASES),
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
