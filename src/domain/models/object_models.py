from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel


@dataclass(frozen=True)
class SpooledObject:
    path: Path
    size_bytes: int
    checksum_sha256: str


class ObjectItem(BaseModel):
    app: str
    key: str
    content_type: str
    size_bytes: int
    checksum_sha256: str
    relative_path: str
    created_at: str
    updated_at: str
