"""Runtime configuration, from the environment only.

Nothing here is read from the repo. On the server the values come from a .env
file next to the checkout (see .env.example) that OpenClaw loads before it
launches the server, or from the service environment if run under systemd.
"""

import os
from pathlib import Path


def _load_dotenv() -> None:
    """Minimal .env loader so the server can be launched by hand for testing.

    Deliberately tiny — no dependency — and it never overrides a variable that
    is already set, so the real environment always wins.
    """
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.is_file():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


_load_dotenv()

DB_PATH = Path(os.environ.get("HORIZON_DB_PATH", "/home/ec2-user/Horisation/_data/market.db"))
EXPORT_DIR = Path(os.environ.get("HORIZON_EXPORT_DIR", "/home/ec2-user/horizon-exports"))
EXPORT_MAX_ROWS = int(os.environ.get("HORIZON_EXPORT_MAX_ROWS", "5000"))
