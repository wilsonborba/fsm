from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse

from src.domain.models.media_models import DeleteResponse, HealthResponse, MediaListResponse, MediaUploadResponse, StatsResponse
from src.domain.services.auth_service import AuthenticatedApp, bearer_scheme


router = APIRouter()


def _authenticated_app_for_route(request: Request, app: str, credentials=Depends(bearer_scheme)) -> AuthenticatedApp:
    return request.app.state.auth_service.authenticate_for_app(app, credentials)


def _authenticated_any_app(request: Request, credentials=Depends(bearer_scheme)) -> AuthenticatedApp:
    return request.app.state.auth_service.authenticate_any(credentials)


@router.get("/health", response_model=HealthResponse)
def healthcheck() -> HealthResponse:
    return HealthResponse(status="ok")


@router.post("/{app}/media", response_model=MediaUploadResponse)
def upload_media(
    request: Request,
    app: str,
    album: str = Form(...),
    file: UploadFile = File(...),
    force: bool = Form(False),
    _: AuthenticatedApp = Depends(_authenticated_app_for_route),
) -> MediaUploadResponse:
    return request.app.state.media_service.upload_media(app, album, file, force_duplicate=force)


@router.get("/{app}/media/{key}")
def get_media(
    request: Request,
    app: str,
    key: str,
    _: AuthenticatedApp = Depends(_authenticated_app_for_route),
) -> FileResponse:
    media_item = request.app.state.media_service.get_media_item(app, key)
    absolute_path = request.app.state.storage_adapter.absolute_path_for_item(media_item)
    return FileResponse(
        absolute_path,
        media_type=media_item.content_type,
        filename=media_item.filename,
        headers={
            "ETag": media_item.checksum_sha256,
        },
    )


@router.get("/{app}/albums/{album}", response_model=MediaListResponse)
def list_album(
    request: Request,
    app: str,
    album: str,
    _: AuthenticatedApp = Depends(_authenticated_app_for_route),
) -> MediaListResponse:
    return request.app.state.media_service.list_album(app, album)


@router.delete("/{app}/media/{key}", response_model=DeleteResponse)
def delete_media(
    request: Request,
    app: str,
    key: str,
    _: AuthenticatedApp = Depends(_authenticated_app_for_route),
) -> DeleteResponse:
    return request.app.state.media_service.delete_media(app, key)


@router.get("/stats", response_model=StatsResponse)
def get_stats(
    request: Request,
    _: AuthenticatedApp = Depends(_authenticated_any_app),
) -> StatsResponse:
    return request.app.state.media_service.get_stats()

