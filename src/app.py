from __future__ import annotations

from fastapi import FastAPI, Request, Response

from src.core.logs import configure_logging
from src.core.settings import load_settings
from src.core.utils import s3_xml
from src.dal.local.object_storage_adapter import ObjectStorageAdapter
from src.dal.local.storage_adapter import LocalStorageAdapter
from src.domain.services.auth_service import AuthService
from src.domain.services.media_service import MediaService
from src.domain.services.s3_auth_service import S3AuthService
from src.domain.services.s3_errors import S3ApiError
from src.domain.services.s3_service import S3Service
from src.presentation.routes.media_routes import router as media_router
from src.presentation.routes.s3_routes import router as s3_router


def create_app() -> FastAPI:
    settings = load_settings()
    configure_logging(settings.log_level)

    storage_adapter = LocalStorageAdapter(settings)
    storage_adapter.ensure_runtime_directories()

    object_storage_adapter = ObjectStorageAdapter(settings)
    object_storage_adapter.ensure_runtime_directories()

    auth_service = AuthService(settings)
    media_service = MediaService(storage_adapter, settings)
    s3_auth_service = S3AuthService(settings)
    s3_service = S3Service(object_storage_adapter)

    app = FastAPI(title=settings.project_name)
    app.state.settings = settings
    app.state.storage_adapter = storage_adapter
    app.state.auth_service = auth_service
    app.state.media_service = media_service
    app.state.object_storage_adapter = object_storage_adapter
    app.state.s3_auth_service = s3_auth_service
    app.state.s3_service = s3_service

    @app.exception_handler(S3ApiError)
    async def s3_api_error_handler(request: Request, exc: S3ApiError) -> Response:
        return Response(
            content=s3_xml.error_xml(exc.code, exc.message),
            media_type="application/xml",
            status_code=exc.status_code,
        )

    app.include_router(media_router)
    app.include_router(s3_router)
    return app

