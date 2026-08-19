# FSM

FSM is a private LAN-first media storage service built for low-resource self-hosted environments.
It exposes a small HTTP API for backend applications that need to upload, read, list and delete image media without depending on external object storage providers.

## Highlights

- Python + FastAPI, no containers.
- Content-addressable local storage (SQLite index) with automatic cross-app deduplication by SHA-256; opt out per upload with `force`.
- Static API key authentication per consumer application.
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

