"""NFC normalization with original-codepoint provenance.

The transformation follows Unicode Standard Annex #15 (Canonical
Decomposition, Canonical Ordering, Canonical Composition) using the
character database exposed by the running interpreter's ``unicodedata``
module.  Alongside the normalized string the module produces, for every
output codepoint, the sorted, deduplicated list of source-codepoint
indices whose material merged into it:

* canonical decomposition inherits the source of the original codepoint;
* canonical reordering never changes provenance;
* canonical composition unions the provenance of every participant.

Hangul syllable decomposition/composition is arithmetic (blocked pairs
simply never recompose) and composition exclusions are honored through
the same unicodedata tables that define NFC for this environment.
"""
import unicodedata

# Hangul canonical constants (Unicode Standard, 3.12 Conjoining Jamo).
_JAMO_L_BASE = 0x1100
_JAMO_V_BASE = 0x1161
_JAMO_T_BASE = 0x11A7
_JAMO_L_COUNT = 19
_JAMO_V_COUNT = 21
_JAMO_T_COUNT = 28
_JAMO_N_COUNT = _JAMO_V_COUNT * _JAMO_T_COUNT
_JAMO_S_COUNT = _JAMO_L_COUNT * _JAMO_N_COUNT
_SYLLABLE_BASE = 0xAC00


def _hangul_nfd(codepoint):
    """Return the arithmetic canonical decomposition of a Hangul syllable."""
    index = codepoint - _SYLLABLE_BASE
    if not 0 <= index < _JAMO_S_COUNT:
        return None
    lead = index // _JAMO_N_COUNT
    vowel = (index % _JAMO_N_COUNT) // _JAMO_T_COUNT
    trail = index % _JAMO_T_COUNT
    result = [_JAMO_L_BASE + lead, _JAMO_V_BASE + vowel]
    if trail:
        result.append(_JAMO_T_BASE + trail)
    return result


def _decompose_codepoint(codepoint):
    hangul = _hangul_nfd(codepoint)
    if hangul is not None:
        return hangul
    mapping = unicodedata.decomposition(chr(codepoint))
    if mapping and not mapping.startswith("<"):
        return [int(token, 16) for token in mapping.split()]
    return [codepoint]


def _full_decomposition(codepoint):
    result = []
    stack = [codepoint]
    while stack:
        current = stack.pop()
        pieces = _decompose_codepoint(current)
        if len(pieces) == 1 and pieces[0] == current:
            result.append(current)
        else:
            stack.extend(reversed(pieces))
    return result


def _merge_sources(left, right):
    return tuple(sorted(set(left) | set(right)))


def _canonical_order(chars, sources):
    """Stable bubble sort by canonical combining class (UAX #15 R2)."""
    changed = True
    while changed:
        changed = False
        for index in range(len(chars) - 1):
            current_class = unicodedata.combining(chr(chars[index]))
            following_class = unicodedata.combining(chr(chars[index + 1]))
            # A starter (ccc 0, including Hangul jamo) never moves and a
            # non-starter never crosses one: only two non-starters swap.
            if following_class != 0 and current_class > following_class:
                chars[index], chars[index + 1] = chars[index + 1], chars[index]
                sources[index], sources[index + 1] = (
                    sources[index + 1], sources[index])
                changed = True


def _build_composition_maps():
    """Derive primary and secondary composition pairs from unicodedata.

    A decomposition mapping whose first part is a starter is a primary
    composite; otherwise it is a secondary composite.  Pairs excluded
    from canonical composition keep their NFD sequence in NFC, so they
    are filtered by asking unicodedata itself how the pair normalizes.
    """
    primary = {}
    secondary = {}
    for codepoint in range(0x110000):
        mapping = unicodedata.decomposition(chr(codepoint))
        if not mapping or mapping.startswith("<"):
            continue
        parts = [int(token, 16) for token in mapping.split()]
        if len(parts) != 2:
            continue
        first, second = parts
        target = chr(codepoint)
        if unicodedata.normalize("NFC", chr(first) + chr(second)) != target:
            continue  # Full_Composition_Exclusion / non-NFC pair
        key = (first, second)
        if unicodedata.combining(chr(first)) == 0:
            primary[key] = codepoint
        else:
            secondary[key] = codepoint
    return primary, secondary


_PRIMARY_PAIRS, _SECONDARY_PAIRS = _build_composition_maps()


def _hangul_pair(first, second, adjacent):
    if not adjacent:
        return None
    if _JAMO_L_BASE <= first < _JAMO_L_BASE + _JAMO_L_COUNT:
        if _JAMO_V_BASE <= second < _JAMO_V_BASE + _JAMO_V_COUNT:
            lead = first - _JAMO_L_BASE
            vowel = second - _JAMO_V_BASE
            return _SYLLABLE_BASE + (lead * _JAMO_V_COUNT + vowel) * _JAMO_T_COUNT
    if _SYLLABLE_BASE <= first < _SYLLABLE_BASE + _JAMO_S_COUNT:
        index = first - _SYLLABLE_BASE
        if index % _JAMO_T_COUNT == 0:
            if _JAMO_T_BASE < second < _JAMO_T_BASE + _JAMO_T_COUNT:
                return first + (second - _JAMO_T_BASE)
    return None


def _compose(chars, sources):
    """Canonical composition over mutable arrays (UAX #15 R3)."""
    if not chars:
        return
    starter = 0
    candidate = 1
    while candidate < len(chars):
        base = chars[starter]
        current = chars[candidate]
        base_class = unicodedata.combining(chr(base))
        current_class = unicodedata.combining(chr(current))
        blocked = False
        if candidate > starter + 1:
            previous_class = unicodedata.combining(chr(chars[candidate - 1]))
            if base_class == 0:
                blocked = previous_class != 0 and previous_class >= current_class
            else:
                blocked = previous_class >= current_class
        if base_class == 0 and not blocked:
            hangul = _hangul_pair(base, current, candidate == starter + 1)
            if hangul is not None:
                chars[starter] = hangul
                sources[starter] = _merge_sources(sources[starter], sources[candidate])
                del chars[candidate]
                del sources[candidate]
                continue
            composed = _PRIMARY_PAIRS.get((base, current))
            if composed is not None:
                chars[starter] = composed
                sources[starter] = _merge_sources(sources[starter], sources[candidate])
                del chars[candidate]
                del sources[candidate]
                continue
        elif not blocked and base_class != 0:
            composed = _SECONDARY_PAIRS.get((base, current))
            if composed is not None and unicodedata.combining(
                    chr(chars[candidate - 1])) != current_class:
                chars[starter] = composed
                sources[starter] = _merge_sources(sources[starter], sources[candidate])
                del chars[candidate]
                del sources[candidate]
                continue
        if current_class == 0:
            starter = candidate
        candidate += 1


def nfc_with_origins(text):
    """Return ``(nfc_text, origins)`` for a whole document.

    ``origins[j]`` is a tuple of ascending, unique original-codepoint
    indices contributing to output position ``j``.
    """
    chars = []
    sources = []
    for index, codepoint in enumerate(ord(char) for char in text):
        for piece in _full_decomposition(codepoint):
            chars.append(piece)
            sources.append((index,))
    _canonical_order(chars, sources)
    _compose(chars, sources)
    normalized = "".join(chr(codepoint) for codepoint in chars)
    expected = unicodedata.normalize("NFC", text)
    if normalized != expected:
        raise RuntimeError("NFC provenance transform disagrees with unicodedata")
    return normalized, [list(source) for source in sources]


def project_spans(origins, start, end):
    """Compress output positions intersecting [start, end) into maximal
    ascending half-open spans."""
    positions = [
        index for index, source in enumerate(origins)
        if any(start <= point < end for point in source)]
    spans = []
    for position in positions:
        if spans and position == spans[-1][1]:
            spans[-1][1] = position + 1
        else:
            spans.append([position, position + 1])
    return spans
