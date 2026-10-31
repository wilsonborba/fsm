#!/usr/bin/env bash
# Generate a new API key for an app and add it to FSM_APP_KEYS in .env,
# without touching any other key already there.
#
# Usage: scripts/generate_app_key.sh <app-name> [--force]
#   --force  overwrite the key if <app-name> already exists

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
ENV_FILE="$ROOT_DIR/.env"
PYTHON_BIN=${PYTHON_BIN:-python3}

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <app-name> [--force]" >&2
  exit 1
fi

APP_NAME="$1"
FORCE=0
if [[ "${2:-}" == "--force" ]]; then
  FORCE=1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "No .env found at $ENV_FILE" >&2
  exit 1
fi

APP_NAME="$APP_NAME" FORCE="$FORCE" ENV_FILE="$ENV_FILE" "$PYTHON_BIN" - <<'PY'
import json
import os
import secrets
import sys

env_file = os.environ["ENV_FILE"]
app_name = os.environ["APP_NAME"]
force = os.environ["FORCE"] == "1"

with open(env_file, "r") as f:
    lines = f.readlines()

key_line_idx = None
current_keys = {}
for i, line in enumerate(lines):
    if line.startswith("FSM_APP_KEYS="):
        key_line_idx = i
        raw = line.rstrip("\n")[len("FSM_APP_KEYS="):]
        current_keys = json.loads(raw) if raw else {}
        break

if key_line_idx is None:
    print("FSM_APP_KEYS= not found in .env", file=sys.stderr)
    sys.exit(1)

if app_name in current_keys and not force:
    print(f"App '{app_name}' already has a key. Pass --force to rotate it.", file=sys.stderr)
    sys.exit(1)

new_key = secrets.token_urlsafe(32)
current_keys[app_name] = new_key
lines[key_line_idx] = f"FSM_APP_KEYS={json.dumps(current_keys)}\n"

with open(env_file, "w") as f:
    f.writelines(lines)

print(f"App: {app_name}")
print(f"Key: {new_key}")
PY
