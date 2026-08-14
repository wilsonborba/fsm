from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.app import create_app


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("FSM_STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setenv("FSM_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("FSM_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("FSM_APP_KEYS", json.dumps({"default": "secret-key", "other": "other-key"}))
    app = create_app()
    return TestClient(app)
