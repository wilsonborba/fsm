from __future__ import annotations

import re


_SLUG_PATTERN = re.compile(r"[^a-zA-Z0-9._-]+")


def normalize_slug(value: str) -> str:
    cleaned = _SLUG_PATTERN.sub("-", value.strip().lower()).strip("-._")
    if not cleaned:
        raise ValueError("Value must contain at least one valid slug character")
    return cleaned

