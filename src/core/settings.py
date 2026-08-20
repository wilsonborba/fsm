from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

from dotenv import load_dotenv

from src.core.utils.files import normalize_slug


@dataclass(frozen=True)
class S3Credential:
    secret_access_key: str
    app: str


@dataclass(frozen=True)
class Settings:
    project_name: str
    host: str
    port: int
    storage_root: Path
    data_root: Path
    runtime_root: Path
    app_keys: Dict[str, str]
    max_upload_bytes: int
    unlimited_uploads: bool
    allowed_mime_types: Tuple[str, ...]
    log_level: str
    s3_credentials: Dict[str, S3Credential]
    s3_region: str
    s3_max_expires_seconds: int


def _load_app_keys(raw_value: str) -> Dict[str, str]:
    if not raw_value:
        return {}

    parsed = json.loads(raw_value)
    if not isinstance(parsed, dict):
        raise ValueError("FSM_APP_KEYS must be a JSON object")

    app_keys: Dict[str, str] = {}
    for app_slug, api_key in parsed.items():
        if not isinstance(app_slug, str) or not isinstance(api_key, str):
            raise ValueError("FSM_APP_KEYS must map strings to strings")
        normalized_slug = app_slug.strip().lower()
        normalized_key = api_key.strip()
        if not normalized_slug or not normalized_key:
            raise ValueError("FSM_APP_KEYS cannot contain empty app slugs or keys")
        app_keys[normalized_slug] = normalized_key
    return app_keys


def _load_s3_credentials(raw_value: str) -> Dict[str, S3Credential]:
    if not raw_value:
        return {}

    parsed = json.loads(raw_value)
    if not isinstance(parsed, dict):
        raise ValueError("FSM_S3_CREDENTIALS must be a JSON object")

    credentials: Dict[str, S3Credential] = {}
    for access_key_id, entry in parsed.items():
        if not isinstance(access_key_id, str) or not isinstance(entry, dict):
            raise ValueError("FSM_S3_CREDENTIALS must map access key ids to objects")
        secret_access_key = entry.get("secret_access_key")
        app = entry.get("app")
        if not isinstance(secret_access_key, str) or not secret_access_key:
            raise ValueError("FSM_S3_CREDENTIALS entries require a non-empty secret_access_key")
        if not isinstance(app, str) or not app:
            raise ValueError("FSM_S3_CREDENTIALS entries require a non-empty app")
        credentials[access_key_id.strip()] = S3Credential(
            secret_access_key=secret_access_key.strip(),
            app=normalize_slug(app),
        )
    return credentials


def load_settings() -> Settings:
    root_dir = Path(__file__).resolve().parents[2]
    load_dotenv(root_dir / ".env")

    storage_root = Path(os.getenv("FSM_STORAGE_ROOT", root_dir / "storage")).expanduser()
    data_root = Path(os.getenv("FSM_DATA_ROOT", root_dir / "data")).expanduser()
    runtime_root = Path(os.getenv("FSM_RUNTIME_ROOT", root_dir / "runtime")).expanduser()
    allowed_mime_types_raw = os.getenv("FSM_ALLOWED_MIME_TYPES", "")

    return Settings(
        project_name="FSM",
        host=os.getenv("FSM_HOST", "0.0.0.0"),
        port=int(os.getenv("FSM_PORT", "8484")),
        storage_root=storage_root,
        data_root=data_root,
        runtime_root=runtime_root,
        app_keys=_load_app_keys(os.getenv("FSM_APP_KEYS", "{}")),
        max_upload_bytes=int(os.getenv("FSM_MAX_UPLOAD_BYTES", str(100 * 1024 * 1024))),
        unlimited_uploads=os.getenv("FSM_UNLIMITED_UPLOADS", "false").strip().lower() == "true",
        allowed_mime_types=tuple(
            mime_type.strip()
            for mime_type in allowed_mime_types_raw.split(",")
            if mime_type.strip()
        ),
        log_level=os.getenv("FSM_LOG_LEVEL", "INFO"),
        s3_credentials=_load_s3_credentials(os.getenv("FSM_S3_CREDENTIALS", "{}")),
        s3_region=os.getenv("FSM_S3_REGION", "us-east-1"),
        s3_max_expires_seconds=int(os.getenv("FSM_S3_MAX_EXPIRES_SECONDS", str(7 * 24 * 3600))),
    )

