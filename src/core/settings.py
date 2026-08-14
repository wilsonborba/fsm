from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

from dotenv import load_dotenv


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
    allowed_mime_types: Tuple[str, ...]
    log_level: str


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


def load_settings() -> Settings:
    root_dir = Path(__file__).resolve().parents[2]
    load_dotenv(root_dir / ".env")

    storage_root = Path(os.getenv("FSM_STORAGE_ROOT", root_dir / "storage")).expanduser()
    data_root = Path(os.getenv("FSM_DATA_ROOT", root_dir / "data")).expanduser()
    runtime_root = Path(os.getenv("FSM_RUNTIME_ROOT", root_dir / "runtime")).expanduser()
    allowed_mime_types_raw = os.getenv(
        "FSM_ALLOWED_MIME_TYPES",
        "image/jpeg,image/png,image/webp,image/gif",
    )

    return Settings(
        project_name="FSM",
        host=os.getenv("FSM_HOST", "0.0.0.0"),
        port=int(os.getenv("FSM_PORT", "8484")),
        storage_root=storage_root,
        data_root=data_root,
        runtime_root=runtime_root,
        app_keys=_load_app_keys(os.getenv("FSM_APP_KEYS", "{}")),
        max_upload_bytes=int(os.getenv("FSM_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024))),
        allowed_mime_types=tuple(
            mime_type.strip()
            for mime_type in allowed_mime_types_raw.split(",")
            if mime_type.strip()
        ),
        log_level=os.getenv("FSM_LOG_LEVEL", "INFO"),
    )

