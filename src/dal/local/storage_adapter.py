from __future__ import annotations

import hashlib
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from fastapi import UploadFile

from src.core.settings import Settings
from src.core.utils.files import normalize_slug
from src.dal.local.db import connect, initialize_schema
from src.domain.models.media_models import MediaItem


class LocalStorageAdapter:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.storage_root = settings.storage_root
        self.data_root = settings.data_root
        self.db_path = self.data_root / "fsm.db"

    def ensure_runtime_directories(self) -> None:
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.settings.runtime_root.mkdir(parents=True, exist_ok=True)
        (self.storage_root / "tmp").mkdir(parents=True, exist_ok=True)
        initialize_schema(self.db_path)

    def _connect(self):
        return connect(self.db_path)

    def _blob_relative_path(self, blob_id: str, suffix: str) -> Path:
        return Path("blobs") / blob_id[:2] / blob_id[2:4] / f"{blob_id}{suffix}"

    def _media_item_from_row(self, row) -> MediaItem:
        return MediaItem(
            key=row["key"],
            app=row["app"],
            album=row["album"],
            filename=row["filename"],
            content_type=row["content_type"],
            size_bytes=row["size_bytes"],
            relative_path=row["relative_path"],
            checksum_sha256=row["content_hash"],
            created_at=row["created_at"],
        )

    _MEDIA_ITEM_SELECT = (
        "SELECT media_items.key, media_items.app, media_items.album, media_items.filename,"
        " media_items.created_at, blobs.content_type, blobs.size_bytes, blobs.relative_path,"
        " blobs.content_hash"
        " FROM media_items JOIN blobs ON blobs.blob_id = media_items.blob_id"
    )

    def save_upload(
        self,
        app_slug: str,
        album: str,
        upload_file: UploadFile,
        force_duplicate: bool = False,
    ) -> MediaItem:
        normalized_app = normalize_slug(app_slug)
        normalized_album = normalize_slug(album)
        now = datetime.now(timezone.utc)
        original_filename = upload_file.filename or "upload"
        suffix = Path(original_filename).suffix.lower()
        if not suffix:
            guessed_extension = mimetypes.guess_extension(upload_file.content_type or "") or ""
            suffix = guessed_extension.lower()

        content_type = upload_file.content_type or "application/octet-stream"
        media_key = uuid4().hex

        temp_dir = self.storage_root / "tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        sha256 = hashlib.sha256()
        total_size = 0
        upload_file.file.seek(0)
        with NamedTemporaryFile("wb", delete=False, dir=str(temp_dir)) as destination:
            temp_path = Path(destination.name)
            while True:
                chunk = upload_file.file.read(1024 * 1024)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > self.settings.max_upload_bytes:
                    destination.close()
                    temp_path.unlink(missing_ok=True)
                    raise ValueError(
                        f"Upload exceeds configured limit of {self.settings.max_upload_bytes} bytes"
                    )
                sha256.update(chunk)
                destination.write(chunk)

        content_hash = sha256.hexdigest()

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")

            existing_blob = None
            if not force_duplicate:
                existing_blob = connection.execute(
                    "SELECT blob_id, relative_path FROM blobs WHERE content_hash = ?"
                    " ORDER BY created_at ASC LIMIT 1",
                    (content_hash,),
                ).fetchone()

            if existing_blob is not None:
                blob_id = existing_blob["blob_id"]
                relative_path = existing_blob["relative_path"]
                temp_path.unlink(missing_ok=True)
                connection.execute(
                    "UPDATE blobs SET refcount = refcount + 1 WHERE blob_id = ?",
                    (blob_id,),
                )
            else:
                # A forced copy gets its own physical identity (content hash plus a
                # unique suffix) so it never shares refcount/lifecycle with an
                # existing blob of identical content, per explicit "force duplicate".
                blob_id = f"{content_hash}-{media_key}" if force_duplicate else content_hash
                relative_path = str(self._blob_relative_path(blob_id, suffix))
                absolute_path = self.storage_root / relative_path
                absolute_path.parent.mkdir(parents=True, exist_ok=True)
                temp_path.replace(absolute_path)
                connection.execute(
                    "INSERT INTO blobs (blob_id, content_hash, relative_path, size_bytes,"
                    " content_type, refcount, created_at) VALUES (?, ?, ?, ?, ?, 1, ?)",
                    (blob_id, content_hash, relative_path, total_size, content_type, now.isoformat()),
                )

            connection.execute(
                "INSERT INTO media_items (app, key, album, filename, blob_id, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (normalized_app, media_key, normalized_album, original_filename, blob_id, now.isoformat()),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            temp_path.unlink(missing_ok=True)
            raise
        finally:
            connection.close()

        return MediaItem(
            key=media_key,
            app=normalized_app,
            album=normalized_album,
            filename=original_filename,
            content_type=content_type,
            size_bytes=total_size,
            relative_path=relative_path,
            checksum_sha256=content_hash,
            created_at=now.isoformat(),
        )

    def get_item(self, app_slug: str, media_key: str) -> Optional[MediaItem]:
        connection = self._connect()
        try:
            row = connection.execute(
                f"{self._MEDIA_ITEM_SELECT} WHERE media_items.app = ? AND media_items.key = ?",
                (normalize_slug(app_slug), media_key),
            ).fetchone()
        finally:
            connection.close()
        return self._media_item_from_row(row) if row else None

    def list_items(self, app_slug: str, album: str) -> List[MediaItem]:
        normalized_album = normalize_slug(album)
        connection = self._connect()
        try:
            rows = connection.execute(
                f"{self._MEDIA_ITEM_SELECT} WHERE media_items.app = ? AND media_items.album = ?"
                " ORDER BY media_items.created_at DESC",
                (normalize_slug(app_slug), normalized_album),
            ).fetchall()
        finally:
            connection.close()
        return [self._media_item_from_row(row) for row in rows]

    def delete_item(self, app_slug: str, media_key: str) -> Optional[MediaItem]:
        normalized_app = normalize_slug(app_slug)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                f"{self._MEDIA_ITEM_SELECT} WHERE media_items.app = ? AND media_items.key = ?",
                (normalized_app, media_key),
            ).fetchone()
            if row is None:
                connection.rollback()
                return None

            media_item = self._media_item_from_row(row)
            connection.execute(
                "DELETE FROM media_items WHERE app = ? AND key = ?",
                (normalized_app, media_key),
            )
            blob_row = connection.execute(
                "UPDATE blobs SET refcount = refcount - 1 WHERE relative_path = ? RETURNING blob_id, refcount",
                (media_item.relative_path,),
            ).fetchone()

            absolute_path = None
            if blob_row is not None and blob_row["refcount"] <= 0:
                connection.execute("DELETE FROM blobs WHERE blob_id = ?", (blob_row["blob_id"],))
                absolute_path = self.storage_root / media_item.relative_path

            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        if absolute_path is not None:
            absolute_path.unlink(missing_ok=True)
            self._cleanup_empty_directories(absolute_path.parent)
        return media_item

    def absolute_path_for_item(self, media_item: MediaItem) -> Path:
        return self.storage_root / media_item.relative_path

    def compute_stats(self) -> Tuple[int, int, Optional[MediaItem], Dict[str, Dict[str, int]]]:
        connection = self._connect()
        try:
            total_row = connection.execute(
                f"SELECT COUNT(*) AS files, COALESCE(SUM(blobs.size_bytes), 0) AS bytes"
                f" FROM media_items JOIN blobs ON blobs.blob_id = media_items.blob_id"
            ).fetchone()
            by_app_rows = connection.execute(
                "SELECT media_items.app AS app, COUNT(*) AS files,"
                " COALESCE(SUM(blobs.size_bytes), 0) AS bytes"
                " FROM media_items JOIN blobs ON blobs.blob_id = media_items.blob_id"
                " GROUP BY media_items.app"
            ).fetchall()
            largest_row = connection.execute(
                f"{self._MEDIA_ITEM_SELECT} ORDER BY blobs.size_bytes DESC LIMIT 1"
            ).fetchone()
        finally:
            connection.close()

        total_files = total_row["files"]
        total_bytes = total_row["bytes"]
        by_app = {row["app"]: {"files": row["files"], "bytes": row["bytes"]} for row in by_app_rows}
        largest_item = self._media_item_from_row(largest_row) if largest_row else None
        return total_files, total_bytes, largest_item, by_app

    def _cleanup_empty_directories(self, start_path: Path) -> None:
        current_path = start_path
        while current_path != self.storage_root and current_path.exists():
            try:
                current_path.rmdir()
            except OSError:
                break
            current_path = current_path.parent
