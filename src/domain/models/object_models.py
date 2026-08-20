from __future__ import annotations

from pydantic import BaseModel


class ObjectItem(BaseModel):
    app: str
    key: str
    content_type: str
    size_bytes: int
    checksum_sha256: str
    relative_path: str
    created_at: str
    updated_at: str
