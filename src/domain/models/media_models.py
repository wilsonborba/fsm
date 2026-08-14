from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel


class MediaItem(BaseModel):
    key: str
    app: str
    album: str
    filename: str
    content_type: str
    size_bytes: int
    relative_path: str
    checksum_sha256: str
    created_at: str


class MediaUploadResponse(BaseModel):
    item: MediaItem


class MediaListResponse(BaseModel):
    app: str
    album: str
    items: List[MediaItem]


class DeleteResponse(BaseModel):
    deleted: bool
    key: str


class AppStats(BaseModel):
    files: int
    bytes: int


class StatsResponse(BaseModel):
    total_files: int
    total_bytes: int
    largest_item: Optional[MediaItem]
    by_app: Dict[str, AppStats]


class HealthResponse(BaseModel):
    status: str


class ErrorResponse(BaseModel):
    detail: str

