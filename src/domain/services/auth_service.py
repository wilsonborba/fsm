from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.core.settings import Settings


bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedApp:
    slug: str
    api_key: str


class AuthService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def authenticate_for_app(
        self,
        app_slug: str,
        credentials: HTTPAuthorizationCredentials | None,
    ) -> AuthenticatedApp:
        expected_key = self.settings.app_keys.get(app_slug)
        provided_key = credentials.credentials if credentials else None
        if expected_key is None or provided_key != expected_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid application credentials",
            )
        return AuthenticatedApp(slug=app_slug, api_key=provided_key)

    def authenticate_any(
        self,
        credentials: HTTPAuthorizationCredentials | None,
    ) -> AuthenticatedApp:
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing authorization header",
            )

        provided_key = credentials.credentials
        for app_slug, expected_key in self.settings.app_keys.items():
            if provided_key == expected_key:
                return AuthenticatedApp(slug=app_slug, api_key=provided_key)

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid application credentials",
        )

