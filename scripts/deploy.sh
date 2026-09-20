#!/bin/bash
# Pull the latest server and make it live. stdio transport means there is no
# service to restart: OpenClaw launches a fresh subprocess on its next tool
# call, so a pull is the whole deploy. (If OpenClaw keeps the subprocess alive
# between calls, restart OpenClaw — see the last step.)
set -euo pipefail

DIR="/home/ec2-user/Horizon_MCP"
VENV="$DIR/.venv"

echo "[1/4] Pulling..."
cd "$DIR"
git fetch origin
git reset --hard origin/main

echo "[2/4] Dependencies..."
if [ ! -x "$VENV/bin/python" ]; then
  python3.11 -m venv "$VENV" 2>/dev/null || python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -e ".[dev]"

echo "[3/4] Smoke test (real database, read-only)..."
"$VENV/bin/python" - <<'PY'
from horizon_mcp.tools.status import db_status
s = db_status()
assert s["ok"], s
print(f"      db ok: {s['tables']} tables, {s['rows_total']} rows, exports -> {s['export_dir']}")
PY

echo "[4/4] Restart OpenClaw so it picks up the new server (only if it caches the subprocess)."
# sudo systemctl restart openclaw   # uncomment once the service name is known
echo "Done."
