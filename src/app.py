from __future__ import annotations

from fastapi import FastAPI

from src.core.logs import configure_logging
from src.core.settings import load_settings
from src.dal.local.storage_adapter import LocalStorageAdapter
from src.domain.services.auth_service import AuthService
from src.domain.services.media_service import MediaService
from src.presentation.routes.media_routes import router as media_router


def create_app() -> FastAPI:
    settings = load_settings()
    configure_logging(settings.log_level)

    storage_adapter = LocalStorageAdapter(settings)
    storage_adapter.ensure_runtime_directories()

    auth_service = AuthService(settings)
    media_service = MediaService(storage_adapter, settings)

    app = FastAPI(title=settings.project_name)
    app.state.settings = settings
    app.state.storage_adapter = storage_adapter
    app.state.auth_service = auth_service
    app.state.media_service = media_service
    app.include_router(media_router)
    return app

