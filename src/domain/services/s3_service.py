from __future__ import annotations

from typing import List

from src.core.utils.files import normalize_object_key, normalize_slug
from src.dal.local.object_storage_adapter import ObjectStorageAdapter
from src.domain.models.object_models import ObjectItem
from src.domain.services.s3_errors import S3ApiError


class S3Service:
    def __init__(self, storage_adapter: ObjectStorageAdapter):
        self.storage_adapter = storage_adapter

    def require_bucket_matches_app(self, bucket: str, authenticated_app: str) -> str:
        normalized_bucket = normalize_slug(bucket)
        if normalized_bucket != authenticated_app:
            raise S3ApiError(403, "AccessDenied", "Credentials are not authorized for this bucket")
        return normalized_bucket

    def put_object(self, app: str, key: str, content_type: str, data: bytes) -> ObjectItem:
        normalized_key = normalize_object_key(key)
        try:
            return self.storage_adapter.put_object(app, normalized_key, content_type or "application/octet-stream", data)
        except ValueError as exc:
            raise S3ApiError(400, "EntityTooLarge", str(exc)) from exc

    def head_object(self, app: str, key: str) -> ObjectItem:
        item = self.storage_adapter.head_object(app, normalize_object_key(key))
        if item is None:
            raise S3ApiError(404, "NoSuchKey", "Object not found")
        return item

    def get_object(self, app: str, key: str) -> ObjectItem:
        return self.head_object(app, key)

    def delete_objects(self, app: str, keys: List[str]) -> List[str]:
        normalized_keys = [normalize_object_key(key) for key in keys]
        return self.storage_adapter.delete_objects(app, normalized_keys)

    def copy_object(self, app: str, source_key: str, dest_key: str) -> ObjectItem:
        item = self.storage_adapter.copy_object(
            app, normalize_object_key(source_key), normalize_object_key(dest_key)
        )
        if item is None:
            raise S3ApiError(404, "NoSuchKey", "Source object not found")
        return item

    def list_objects(self, app: str, prefix: str = "") -> List[ObjectItem]:
        return self.storage_adapter.list_objects(app, prefix)
