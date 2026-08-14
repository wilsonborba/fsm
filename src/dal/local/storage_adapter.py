from __future__ import annotations

import hashlib
import json
import mimetypes
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from fastapi import UploadFile

from src.core.settings import Settings
from src.core.utils.files import atomic_write_json, normalize_slug
from src.domain.models.media_models import MediaItem


class LocalStorageAdapter:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.storage_root = settings.storage_root
        self.data_root = settings.data_root

    def ensure_runtime_directories(self) -> None:
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.settings.runtime_root.mkdir(parents=True, exist_ok=True)

    def index_path_for_app(self, app_slug: str) -> Path:
        return self.data_root / f"{normalize_slug(app_slug)}.json"

    def load_index(self, app_slug: str) -> Dict[str, Dict[str, str]]:
        index_path = self.index_path_for_app(app_slug)
        if not index_path.exists():
            return {}
        with index_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def save_index(self, app_slug: str, index_payload: Dict[str, Dict[str, str]]) -> None:
        atomic_write_json(self.index_path_for_app(app_slug), index_payload)

    def save_upload(self, app_slug: str, album: str, upload_file: UploadFile) -> MediaItem:
        normalized_app = normalize_slug(app_slug)
        normalized_album = normalize_slug(album)
        now = datetime.now(timezone.utc)
        original_filename = upload_file.filename or "upload"
        suffix = Path(original_filename).suffix.lower()
        if not suffix:
            guessed_extension = mimetypes.guess_extension(upload_file.content_type or "") or ""
            suffix = guessed_extension.lower()

        media_key = uuid4().hex
        relative_path = Path(normalized_app) / normalized_album / now.strftime("%Y") / now.strftime("%m") / f"{media_key}{suffix}"
        absolute_path = self.storage_root / relative_path
        absolute_path.parent.mkdir(parents=True, exist_ok=True)

        sha256 = hashlib.sha256()
        total_size = 0
        upload_file.file.seek(0)
        with absolute_path.open("wb") as destination:
            while True:
                chunk = upload_file.file.read(1024 * 1024)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > self.settings.max_upload_bytes:
                    destination.close()
                    absolute_path.unlink(missing_ok=True)
                    raise ValueError(
                        f"Upload exceeds configured limit of {self.settings.max_upload_bytes} bytes"
                    )
                sha256.update(chunk)
                destination.write(chunk)

        media_item = MediaItem(
            key=media_key,
            app=normalized_app,
            album=normalized_album,
            filename=original_filename,
            content_type=upload_file.content_type or "application/octet-stream",
            size_bytes=total_size,
            relative_path=str(relative_path),
            checksum_sha256=sha256.hexdigest(),
            created_at=now.isoformat(),
        )

        current_index = self.load_index(normalized_app)
        current_index[media_key] = media_item.dict()
        self.save_index(normalized_app, current_index)
        return media_item

    def get_item(self, app_slug: str, media_key: str) -> Optional[MediaItem]:
        current_index = self.load_index(app_slug)
        payload = current_index.get(media_key)
        if not payload:
            return None
        return MediaItem(**payload)

    def list_items(self, app_slug: str, album: str) -> List[MediaItem]:
        normalized_album = normalize_slug(album)
        current_index = self.load_index(app_slug)
        items = [MediaItem(**payload) for payload in current_index.values() if payload["album"] == normalized_album]
        return sorted(items, key=lambda item: item.created_at, reverse=True)

    def delete_item(self, app_slug: str, media_key: str) -> Optional[MediaItem]:
        current_index = self.load_index(app_slug)
        payload = current_index.pop(media_key, None)
        if not payload:
            return None

        media_item = MediaItem(**payload)
        absolute_path = self.storage_root / media_item.relative_path
        absolute_path.unlink(missing_ok=True)
        self.save_index(app_slug, current_index)
        self._cleanup_empty_directories(absolute_path.parent)
        return media_item

    def absolute_path_for_item(self, media_item: MediaItem) -> Path:
        return self.storage_root / media_item.relative_path

    def compute_stats(self) -> Tuple[int, int, Optional[MediaItem], Dict[str, Dict[str, int]]]:
        total_files = 0
        total_bytes = 0
        largest_item: Optional[MediaItem] = None
        by_app: Dict[str, Dict[str, int]] = {}

        for index_path in sorted(self.data_root.glob("*.json")):
            with index_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            app_files = 0
            app_bytes = 0
            for item_payload in payload.values():
                media_item = MediaItem(**item_payload)
                total_files += 1
                total_bytes += media_item.size_bytes
                app_files += 1
                app_bytes += media_item.size_bytes
                if largest_item is None or media_item.size_bytes > largest_item.size_bytes:
                    largest_item = media_item
            by_app[index_path.stem] = {
                "files": app_files,
                "bytes": app_bytes,
            }

        return total_files, total_bytes, largest_item, by_app

    def _cleanup_empty_directories(self, start_path: Path) -> None:
        current_path = start_path
        while current_path != self.storage_root and current_path.exists():
            try:
                current_path.rmdir()
            except OSError:
                break
            current_path = current_path.parent

