#!/bin/bash
# Pull the latest server and make it live. Works on the Mac mini (OpenClaw's
# machine, data over SSH) and on the EC2 box (data local) alike.
#
# stdio transport means there is no service to restart: OpenClaw launches a
# fresh subprocess on its next tool call, so a pull is the whole deploy.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$DIR/.venv"

# The mcp SDK needs Python >= 3.10. macOS ships 3.9 as `python3`, so look for
# a newer one first (Homebrew), then fall back and let the version check speak.
pick_python() {
  for c in python3.13 python3.12 python3.11 python3.10 \
           /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
    if command -v "$c" >/dev/null 2>&1; then
      if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'; then
        echo "$c"; return 0
      fi
    fi
  done
  return 1
}

echo "[1/4] Pulling..."
cd "$DIR"
git fetch origin
git reset --hard origin/main

echo "[2/4] Dependencies..."
if [ ! -x "$VENV/bin/python" ]; then
  PY="$(pick_python)" || { echo "      No Python >= 3.10 found. On a Mac: brew install python@3.11"; exit 1; }
  echo "      creating venv with $PY ($("$PY" --version))"
  "$PY" -m venv "$VENV"
fi
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -e ".[dev]"

echo "[3/4] Smoke test (read-only)..."
if grep -qs '^HORIZON_DB_SSH=.\+' "$DIR/.env"; then
  HOST="$(grep '^HORIZON_DB_SSH=' "$DIR/.env" | cut -d= -f2 | cut -d: -f1)"
  echo "      remote mode: checking ssh to '$HOST' first"
  ssh -o BatchMode=yes -o ConnectTimeout=10 "$HOST" 'echo "      ssh ok: $(hostname)"' \
    || { echo "      ssh to '$HOST' failed. Check ~/.ssh/config and the key. Nothing else was touched."; exit 1; }
fi
"$VENV/bin/python" - <<'PY'
from horizon_mcp.tools.status import db_status
s = db_status()
assert s["ok"], s
print(f"      db ok ({s['source']}): {s['tables']} tables, {s['rows_total']} rows, exports -> {s['export_dir']}")
PY

echo "[4/4] Done. stdio has no service to restart."
echo "      If OpenClaw keeps the subprocess alive between calls, restart OpenClaw now."
