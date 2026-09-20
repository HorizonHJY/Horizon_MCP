"""Runtime configuration, from the environment only.

Nothing here is read from the repo. The values come from a .env file next to
the checkout (see .env.example) that is loaded below, or from the process
environment OpenClaw sets when it launches the server — the environment wins.

Two deployments share this file:

  on the server itself     HORIZON_DB_PATH points at the live database
  on the Mac with OpenClaw HORIZON_DB_SSH names the server and remote path;
                           HORIZON_DB_PATH is then where the pulled snapshot
                           lives locally
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

# `host:/remote/path`. Empty means the database is a local file.
DB_SSH = os.environ.get("HORIZON_DB_SSH", "").strip()

DB_PATH = Path(os.environ.get(
    "HORIZON_DB_PATH",
    "~/horizon-exports/market.snapshot.db" if DB_SSH else "/home/ec2-user/Horisation/_data/market.db",
)).expanduser()
EXPORT_DIR = Path(os.environ.get("HORIZON_EXPORT_DIR", "~/horizon-exports")).expanduser()
EXPORT_MAX_ROWS = int(os.environ.get("HORIZON_EXPORT_MAX_ROWS", "5000"))

# A snapshot younger than this is reused rather than re-fetched.
SNAPSHOT_MAX_AGE = int(os.environ.get("HORIZON_SNAPSHOT_MAX_AGE", "300"))
