from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import List, Optional
from uuid import uuid4

from src.core.settings import Settings
from src.dal.local.db import connect
from src.domain.models.object_models import ObjectItem


class ObjectStorageAdapter:
    """Key-addressed storage: the caller picks the key, PUT overwrites."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.storage_root = settings.storage_root
        self.data_root = settings.data_root
        self.db_path = self.data_root / "fsm.db"

    def ensure_runtime_directories(self) -> None:
        self.storage_root.mkdir(parents=True, exist_ok=True)
        (self.storage_root / "objects").mkdir(parents=True, exist_ok=True)
        (self.storage_root / "tmp").mkdir(parents=True, exist_ok=True)

    def _connect(self):
        return connect(self.db_path)

    def _relative_path_for(self, app: str, key: str) -> Path:
        digest = hashlib.sha256(f"{app}:{key}".encode("utf-8")).hexdigest()
        suffix = Path(key).suffix.lower()
        return Path("objects") / app / digest[:2] / digest[2:4] / f"{digest}{suffix}"

    def _row_to_item(self, row) -> ObjectItem:
        return ObjectItem(
            app=row["app"],
            key=row["key"],
            content_type=row["content_type"],
            size_bytes=row["size_bytes"],
            checksum_sha256=row["content_hash"],
            relative_path=row["relative_path"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def put_object(self, app: str, key: str, content_type: str, data: bytes) -> ObjectItem:
        if not self.settings.unlimited_uploads and len(data) > self.settings.max_upload_bytes:
            raise ValueError(f"Upload exceeds configured limit of {self.settings.max_upload_bytes} bytes")

        now = datetime.now(timezone.utc).isoformat()
        checksum = hashlib.sha256(data).hexdigest()
        relative_path = self._relative_path_for(app, key)
        absolute_path = self.storage_root / relative_path
        absolute_path.parent.mkdir(parents=True, exist_ok=True)

        temp_dir = self.storage_root / "tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("wb", delete=False, dir=str(temp_dir)) as destination:
            temp_path = Path(destination.name)
            destination.write(data)

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT relative_path FROM objects WHERE app = ? AND key = ?", (app, key)
            ).fetchone()

            temp_path.replace(absolute_path)

            if existing is not None:
                connection.execute(
                    "UPDATE objects SET relative_path = ?, size_bytes = ?, content_type = ?,"
                    " content_hash = ?, updated_at = ? WHERE app = ? AND key = ?",
                    (str(relative_path), len(data), content_type, checksum, now, app, key),
                )
            else:
                connection.execute(
                    "INSERT INTO objects (app, key, relative_path, size_bytes, content_type,"
                    " content_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (app, key, str(relative_path), len(data), content_type, checksum, now, now),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            temp_path.unlink(missing_ok=True)
            raise
        finally:
            connection.close()

        if existing is not None and existing["relative_path"] != str(relative_path):
            (self.storage_root / existing["relative_path"]).unlink(missing_ok=True)

        return ObjectItem(
            app=app,
            key=key,
            content_type=content_type,
            size_bytes=len(data),
            checksum_sha256=checksum,
            relative_path=str(relative_path),
            created_at=now,
            updated_at=now,
        )

    def head_object(self, app: str, key: str) -> Optional[ObjectItem]:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM objects WHERE app = ? AND key = ?", (app, key)
            ).fetchone()
        finally:
            connection.close()
        return self._row_to_item(row) if row else None

    def get_object(self, app: str, key: str) -> Optional[ObjectItem]:
        return self.head_object(app, key)

    def absolute_path_for_item(self, item: ObjectItem) -> Path:
        return self.storage_root / item.relative_path

    def delete_object(self, app: str, key: str) -> bool:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT relative_path FROM objects WHERE app = ? AND key = ?", (app, key)
            ).fetchone()
            if row is None:
                connection.rollback()
                return False
            connection.execute("DELETE FROM objects WHERE app = ? AND key = ?", (app, key))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        (self.storage_root / row["relative_path"]).unlink(missing_ok=True)
        return True

    def delete_objects(self, app: str, keys: List[str]) -> List[str]:
        return [key for key in keys if self.delete_object(app, key)]

    def copy_object(self, app: str, source_key: str, dest_key: str) -> Optional[ObjectItem]:
        source = self.head_object(app, source_key)
        if source is None:
            return None
        data = (self.storage_root / source.relative_path).read_bytes()
        return self.put_object(app, dest_key, source.content_type, data)

    def list_objects(self, app: str, prefix: str = "") -> List[ObjectItem]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM objects WHERE app = ? AND key LIKE ? ESCAPE '\\' ORDER BY key ASC",
                (app, self._like_prefix(prefix)),
            ).fetchall()
        finally:
            connection.close()
        return [self._row_to_item(row) for row in rows]

    @staticmethod
    def _like_prefix(prefix: str) -> str:
        escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"{escaped}%"
