from .records import AnnotationRecord


def validate_codepoint_interval(start, end, codepoint_count):
    if type(start) is not int or type(end) is not int:
        raise ValueError("annotation coordinates must be non-boolean integers")
    if not 0 <= start < end <= codepoint_count:
        raise ValueError("annotation must be a nonempty in-bounds interval")


def validate_annotations(records, codepoint_count):
    if type(codepoint_count) is not int or codepoint_count < 0:
        raise ValueError("invalid document size")
    seen = set()
    for record in records:
        if not isinstance(record, AnnotationRecord):
            raise ValueError("parsed annotation required")
        if record.id in seen:
            raise ValueError("duplicate annotation id")
        seen.add(record.id)
        validate_codepoint_interval(record.start, record.end, codepoint_count)
    return tuple(records)
