from __future__ import annotations

import json
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


_SLUG_PATTERN = re.compile(r"[^a-zA-Z0-9._-]+")


def normalize_slug(value: str) -> str:
    cleaned = _SLUG_PATTERN.sub("-", value.strip().lower()).strip("-._")
    if not cleaned:
        raise ValueError("Value must contain at least one valid slug character")
    return cleaned


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=str(path.parent)) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.flush()
        temp_path = Path(handle.name)
    temp_path.replace(path)

