from __future__ import annotations

from pathlib import Path


def _blob_files(tmp_path: Path) -> list[Path]:
    blobs_dir = tmp_path / "storage" / "blobs"
    if not blobs_dir.exists():
        return []
    return sorted(path for path in blobs_dir.rglob("*") if path.is_file())


def test_healthcheck(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_upload_requires_auth(client):
    response = client.post(
        "/default/media",
        data={"album": "sample"},
        files={"file": ("image.png", b"pngdata", "image/png")},
    )
    assert response.status_code == 401


def test_media_lifecycle_and_stats(client):
    upload_response = client.post(
        "/default/media",
        headers={"Authorization": "Bearer secret-key"},
        data={"album": "sample-album"},
        files={"file": ("image.png", b"pngdata", "image/png")},
    )

    assert upload_response.status_code == 200
    uploaded_item = upload_response.json()["item"]
    media_key = uploaded_item["key"]

    list_response = client.get(
        "/default/albums/sample-album",
        headers={"Authorization": "Bearer secret-key"},
    )
    assert list_response.status_code == 200
    assert len(list_response.json()["items"]) == 1

    download_response = client.get(
        f"/default/media/{media_key}",
        headers={"Authorization": "Bearer secret-key"},
    )
    assert download_response.status_code == 200
    assert download_response.content == b"pngdata"
    assert download_response.headers["etag"]

    stats_response = client.get(
        "/stats",
        headers={"Authorization": "Bearer secret-key"},
    )
    assert stats_response.status_code == 200
    stats_payload = stats_response.json()
    assert stats_payload["total_files"] == 1
    assert stats_payload["by_app"]["default"]["files"] == 1

    delete_response = client.delete(
        f"/default/media/{media_key}",
        headers={"Authorization": "Bearer secret-key"},
    )
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True, "key": media_key}


def test_app_key_is_scoped_to_route_app(client):
    response = client.post(
        "/other/media",
        headers={"Authorization": "Bearer secret-key"},
        data={"album": "sample"},
        files={"file": ("image.png", b"pngdata", "image/png")},
    )
    assert response.status_code == 401


def test_rejects_unsupported_media_type(client):
    response = client.post(
        "/default/media",
        headers={"Authorization": "Bearer secret-key"},
        data={"album": "sample"},
        files={"file": ("file.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400


def test_identical_uploads_deduplicate_to_a_single_blob(client, tmp_path):
    payload = {"file": ("photo.png", b"identical-bytes", "image/png")}

    first = client.post(
        "/default/media",
        headers={"Authorization": "Bearer secret-key"},
        data={"album": "sample"},
        files=payload,
    )
    second = client.post(
        "/other/media",
        headers={"Authorization": "Bearer other-key"},
        data={"album": "sample"},
        files=payload,
    )
    assert first.status_code == 200
    assert second.status_code == 200

    first_key = first.json()["item"]["key"]
    second_key = second.json()["item"]["key"]
    assert first_key != second_key
    assert first.json()["item"]["checksum_sha256"] == second.json()["item"]["checksum_sha256"]
    assert len(_blob_files(tmp_path)) == 1

    delete_response = client.delete(
        f"/default/media/{first_key}",
        headers={"Authorization": "Bearer secret-key"},
    )
    assert delete_response.status_code == 200
    assert len(_blob_files(tmp_path)) == 1

    download_response = client.get(
        f"/other/media/{second_key}",
        headers={"Authorization": "Bearer other-key"},
    )
    assert download_response.status_code == 200
    assert download_response.content == b"identical-bytes"

    client.delete(f"/other/media/{second_key}", headers={"Authorization": "Bearer other-key"})
    assert len(_blob_files(tmp_path)) == 0


def test_force_flag_creates_independent_copy(client, tmp_path):
    payload = {"file": ("photo.png", b"same-bytes-forced", "image/png")}

    first = client.post(
        "/default/media",
        headers={"Authorization": "Bearer secret-key"},
        data={"album": "sample"},
        files=payload,
    )
    second = client.post(
        "/default/media",
        headers={"Authorization": "Bearer secret-key"},
        data={"album": "sample", "force": "true"},
        files=payload,
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert len(_blob_files(tmp_path)) == 2

    first_key = first.json()["item"]["key"]
    second_key = second.json()["item"]["key"]

    client.delete(f"/default/media/{second_key}", headers={"Authorization": "Bearer secret-key"})
    assert len(_blob_files(tmp_path)) == 1

    download_response = client.get(
        f"/default/media/{first_key}",
        headers={"Authorization": "Bearer secret-key"},
    )
    assert download_response.status_code == 200
    assert download_response.content == b"same-bytes-forced"

