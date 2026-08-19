from __future__ import annotations

from fastapi import HTTPException, UploadFile, status

from src.core.settings import Settings
from src.core.utils.files import normalize_slug
from src.dal.local.storage_adapter import LocalStorageAdapter
from src.domain.models.media_models import DeleteResponse, MediaItem, MediaListResponse, MediaUploadResponse, StatsResponse, AppStats


class MediaService:
    def __init__(self, storage_adapter: LocalStorageAdapter, settings: Settings):
        self.storage_adapter = storage_adapter
        self.settings = settings

    def upload_media(
        self,
        app_slug: str,
        album: str,
        upload_file: UploadFile,
        force_duplicate: bool = False,
    ) -> MediaUploadResponse:
        normalized_app = normalize_slug(app_slug)
        normalized_album = normalize_slug(album)
        if upload_file.content_type not in self.settings.allowed_mime_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported media type: {upload_file.content_type}",
            )
        try:
            media_item = self.storage_adapter.save_upload(
                normalized_app, normalized_album, upload_file, force_duplicate=force_duplicate
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return MediaUploadResponse(item=media_item)

    def get_media_item(self, app_slug: str, media_key: str) -> MediaItem:
        normalized_app = normalize_slug(app_slug)
        media_item = self.storage_adapter.get_item(normalized_app, media_key)
        if not media_item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media item not found")
        return media_item

    def list_album(self, app_slug: str, album: str) -> MediaListResponse:
        normalized_app = normalize_slug(app_slug)
        normalized_album = normalize_slug(album)
        items = self.storage_adapter.list_items(normalized_app, normalized_album)
        return MediaListResponse(app=normalized_app, album=normalized_album, items=items)

    def delete_media(self, app_slug: str, media_key: str) -> DeleteResponse:
        normalized_app = normalize_slug(app_slug)
        media_item = self.storage_adapter.delete_item(normalized_app, media_key)
        if not media_item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media item not found")
        return DeleteResponse(deleted=True, key=media_key)

    def get_stats(self) -> StatsResponse:
        total_files, total_bytes, largest_item, by_app = self.storage_adapter.compute_stats()
        return StatsResponse(
            total_files=total_files,
            total_bytes=total_bytes,
            largest_item=largest_item,
            by_app={app_slug: AppStats(**stats) for app_slug, stats in by_app.items()},
        )

