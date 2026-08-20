from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path

import boto3
import httpx
import pytest
import uvicorn
from botocore.config import Config
from botocore.exceptions import ClientError

ACCESS_KEY_ID = "AKIDPLANETEST"
SECRET_ACCESS_KEY = "supersecret"
BUCKET = "plane"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture()
def live_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FSM_STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setenv("FSM_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("FSM_RUNTIME_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("FSM_APP_KEYS", json.dumps({"plane": "plane-bearer-key"}))
    monkeypatch.setenv(
        "FSM_S3_CREDENTIALS",
        json.dumps({ACCESS_KEY_ID: {"secret_access_key": SECRET_ACCESS_KEY, "app": "plane"}}),
    )
    monkeypatch.setenv("FSM_S3_REGION", "us-east-1")

    from src.app import create_app

    app = create_app()
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    else:
        raise RuntimeError("live server did not start in time")

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=5)


def _s3_client(base_url: str, access_key_id: str = ACCESS_KEY_ID, secret_access_key: str = SECRET_ACCESS_KEY):
    return boto3.client(
        "s3",
        endpoint_url=base_url,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name="us-east-1",
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path", "payload_signing_enabled": False},
        ),
    )


def test_put_get_head_delete_object(live_server):
    client = _s3_client(live_server)

    client.put_object(Bucket=BUCKET, Key="docs/hello.txt", Body=b"hello world", ContentType="text/plain")

    head = client.head_object(Bucket=BUCKET, Key="docs/hello.txt")
    assert head["ContentLength"] == len(b"hello world")

    obj = client.get_object(Bucket=BUCKET, Key="docs/hello.txt")
    assert obj["Body"].read() == b"hello world"

    client.delete_object(Bucket=BUCKET, Key="docs/hello.txt")
    with pytest.raises(ClientError):
        client.head_object(Bucket=BUCKET, Key="docs/hello.txt")


def test_put_overwrites_existing_key(live_server):
    client = _s3_client(live_server)

    client.put_object(Bucket=BUCKET, Key="avatar.png", Body=b"v1", ContentType="image/png")
    client.put_object(Bucket=BUCKET, Key="avatar.png", Body=b"v2-longer", ContentType="image/png")

    obj = client.get_object(Bucket=BUCKET, Key="avatar.png")
    assert obj["Body"].read() == b"v2-longer"


def test_copy_object(live_server):
    client = _s3_client(live_server)
    client.put_object(Bucket=BUCKET, Key="source.txt", Body=b"copy-me", ContentType="text/plain")

    client.copy_object(Bucket=BUCKET, CopySource={"Bucket": BUCKET, "Key": "source.txt"}, Key="dest.txt")

    obj = client.get_object(Bucket=BUCKET, Key="dest.txt")
    assert obj["Body"].read() == b"copy-me"


def test_batch_delete(live_server):
    client = _s3_client(live_server)
    client.put_object(Bucket=BUCKET, Key="a.txt", Body=b"a")
    client.put_object(Bucket=BUCKET, Key="b.txt", Body=b"b")

    client.delete_objects(Bucket=BUCKET, Delete={"Objects": [{"Key": "a.txt"}, {"Key": "b.txt"}]})

    with pytest.raises(ClientError):
        client.head_object(Bucket=BUCKET, Key="a.txt")
    with pytest.raises(ClientError):
        client.head_object(Bucket=BUCKET, Key="b.txt")


def test_list_objects_v2(live_server):
    client = _s3_client(live_server)
    client.put_object(Bucket=BUCKET, Key="albums/x.png", Body=b"x")
    client.put_object(Bucket=BUCKET, Key="albums/y.png", Body=b"y")
    client.put_object(Bucket=BUCKET, Key="other/z.png", Body=b"z")

    response = client.list_objects_v2(Bucket=BUCKET, Prefix="albums/")
    keys = sorted(item["Key"] for item in response["Contents"])
    assert keys == ["albums/x.png", "albums/y.png"]


def test_presigned_post_upload(live_server):
    client = _s3_client(live_server)
    presigned = client.generate_presigned_post(
        Bucket=BUCKET,
        Key="uploads/browser.txt",
        Fields={"Content-Type": "text/plain"},
        Conditions=[
            {"bucket": BUCKET},
            ["content-length-range", 1, 1000],
            {"Content-Type": "text/plain"},
        ],
        ExpiresIn=3600,
    )

    response = httpx.post(
        presigned["url"],
        data=presigned["fields"],
        files={"file": ("browser.txt", b"from-the-browser", "text/plain")},
    )
    assert response.status_code == 204

    obj = client.get_object(Bucket=BUCKET, Key="uploads/browser.txt")
    assert obj["Body"].read() == b"from-the-browser"


def test_presigned_get_download(live_server):
    client = _s3_client(live_server)
    client.put_object(Bucket=BUCKET, Key="shared.txt", Body=b"shared-bytes", ContentType="text/plain")

    url = client.generate_presigned_url("get_object", Params={"Bucket": BUCKET, "Key": "shared.txt"}, ExpiresIn=60)
    response = httpx.get(url)
    assert response.status_code == 200
    assert response.content == b"shared-bytes"


def test_bucket_must_match_credential_app(live_server):
    client = _s3_client(live_server)
    with pytest.raises(ClientError) as exc_info:
        client.put_object(Bucket="some-other-app", Key="x.txt", Body=b"x")
    assert exc_info.value.response["ResponseMetadata"]["HTTPStatusCode"] == 403


def test_unknown_access_key_rejected(live_server):
    client = _s3_client(live_server, access_key_id="UNKNOWNKEY", secret_access_key="whatever")
    with pytest.raises(ClientError) as exc_info:
        client.put_object(Bucket=BUCKET, Key="x.txt", Body=b"x")
    assert exc_info.value.response["ResponseMetadata"]["HTTPStatusCode"] == 403
