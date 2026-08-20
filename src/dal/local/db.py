from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS blobs (
    blob_id TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    content_type TEXT NOT NULL,
    refcount INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_blobs_content_hash ON blobs (content_hash);

CREATE TABLE IF NOT EXISTS media_items (
    app TEXT NOT NULL,
    key TEXT NOT NULL,
    album TEXT NOT NULL,
    filename TEXT NOT NULL,
    blob_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (app, key),
    FOREIGN KEY (blob_id) REFERENCES blobs (blob_id)
);

CREATE INDEX IF NOT EXISTS idx_media_items_app_album ON media_items (app, album);

CREATE TABLE IF NOT EXISTS objects (
    app TEXT NOT NULL,
    key TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    content_type TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (app, key)
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=30000")
    connection.row_factory = sqlite3.Row
    return connection


def initialize_schema(db_path: Path) -> None:
    connection = connect(db_path)
    try:
        connection.executescript(SCHEMA)
        connection.commit()
    finally:
        connection.close()
