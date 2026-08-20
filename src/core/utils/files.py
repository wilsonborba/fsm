from __future__ import annotations

import re
from pathlib import PurePosixPath


_SLUG_PATTERN = re.compile(r"[^a-zA-Z0-9._-]+")


def normalize_slug(value: str) -> str:
    cleaned = _SLUG_PATTERN.sub("-", value.strip().lower()).strip("-._")
    if not cleaned:
        raise ValueError("Value must contain at least one valid slug character")
    return cleaned


def normalize_object_key(value: str) -> str:
    """Sanitize an S3-style object key, preserving '/' as a path separator.

    Rejects traversal ('..'), absolute paths, and empty segments so the key
    can be joined directly onto a storage root without escaping it.
    """
    stripped = value.strip().strip("/")
    if not stripped:
        raise ValueError("Object key must contain at least one valid segment")

    segments = []
    for raw_segment in stripped.split("/"):
        segment = raw_segment.strip()
        if not segment or segment in (".", ".."):
            raise ValueError(f"Invalid object key segment: {raw_segment!r}")
        segments.append(segment)

    return str(PurePosixPath(*segments))

