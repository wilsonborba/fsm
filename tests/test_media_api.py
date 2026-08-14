from __future__ import annotations


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

