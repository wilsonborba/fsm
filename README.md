# FSM

FSM is a private LAN-first media storage service built for low-resource self-hosted environments.
It exposes a small HTTP API for backend applications that need to upload, read, list and delete image media without depending on external object storage providers.

## Highlights

- Python + FastAPI, no containers.
- Content-addressable local storage (SQLite index) with automatic cross-app deduplication by SHA-256; opt out per upload with `force`.
- Static API key authentication per consumer application.
- Minimal S3-compatible API (path-style, SigV4) alongside the media API, for apps that already speak `boto3`/`django-storages`.
- `systemd`-managed deployment through a single `./install` script.
- Safe default behavior for private network usage.

## Project structure

```text
src/
├── core/
├── dal/local/
├── domain/models/
├── domain/services/
├── presentation/routes/
├── app.py
└── main.py
tests/
```

## Requirements

- Linux with `python3` available.
- `systemd` for service management.
- `sudo` access for service installation.
- Optional: `ufw` for firewall rules.

## Quick start

```bash
git clone <your-repo-url>
cd fsm
./install
```

The install script:

- creates `.venv`
- installs Python dependencies
- generates `.env` if absent
- installs `fsm-application.service`
- enables and starts the service
- optionally configures `ufw` LAN rules when `ufw` is installed and active

## Configuration

Only secrets and environment-specific private values live in `.env`.

Example:

```env
FSM_HOST=0.0.0.0
FSM_PORT=8484
FSM_APP_KEYS={"default":"replace-me"}
```

Main non-secret defaults live in `src/core/settings.py`.

## API

Authentication uses `Authorization: Bearer <api-key>`.

- `POST /{app}/media`
  - multipart fields: `album`, `file`, `force` (optional, default `false`; forces an independent physical copy instead of deduplicating against identical content already stored)
- `GET /{app}/media/{key}`
- `GET /{app}/albums/{album}`
- `DELETE /{app}/media/{key}`
- `GET /stats`
- `GET /health`

### Upload example

```bash
curl -X POST "http://127.0.0.1:8484/default/media" \
  -H "Authorization: Bearer <api-key>" \
  -F "album=sample" \
  -F "file=@image.png"
```

## S3-compatible API

A separate, additive contract for apps that already talk to S3 via `boto3` (e.g. Django's `django-storages`). Bucket = app slug. Auth is AWS SigV4 (header, presigned query, and presigned POST policy), configured through `FSM_S3_CREDENTIALS` (access key id -> secret + app), independent from the `FSM_APP_KEYS` bearer tokens used by the media API.

Supported operations only — no ACLs, no bucket policies, no multipart upload:

- `PUT /{bucket}/{key}` — put object (also handles `x-amz-copy-source` for COPY)
- `GET /{bucket}/{key}` — get object (header-signed or presigned query)
- `HEAD /{bucket}/{key}` — object metadata
- `DELETE /{bucket}/{key}` — delete a single object
- `POST /{bucket}?delete` — batch delete (XML body)
- `POST /{bucket}` — presigned POST policy upload (browser direct upload)
- `GET /{bucket}?list-type=2` — `ListObjectsV2`, optionally with `prefix`

```python
import boto3
from botocore.config import Config

client = boto3.client(
    "s3",
    endpoint_url="http://127.0.0.1:8484",
    aws_access_key_id="<access-key-id>",
    aws_secret_access_key="<secret-access-key>",
    region_name="us-east-1",
    config=Config(signature_version="s3v4", s3={"addressing_style": "path", "payload_signing_enabled": False}),
)
client.put_object(Bucket="default", Key="avatars/user-1.png", Body=b"...", ContentType="image/png")
```

Uploads via `upload_fileobj`/`TransferManager` must keep `multipart_threshold` above the configured upload cap (`FSM_MAX_UPLOAD_BYTES`) — multipart upload is not implemented.

## Service operations

```bash
sudo systemctl status fsm-application
sudo systemctl restart fsm-application
journalctl -u fsm-application -f
```

## Uninstall

```bash
./uninstall
```

Use `./uninstall --purge-data` to also remove generated storage/runtime data.

