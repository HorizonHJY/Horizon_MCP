"""Where the database actually comes from.

Two deployments, one code path:

  local   HORIZON_DB_SSH unset. The database is a file on this machine
          (the server itself). Nothing happens here; the path is returned.

  remote  HORIZON_DB_SSH=host:/path/to/market.db. This machine (the Mac
          mini running OpenClaw) pulls a SNAPSHOT of the database over SSH
          into HORIZON_DB_PATH and every tool reads that. Snapshots younger
          than HORIZON_SNAPSHOT_MAX_AGE seconds are reused, so a run of tool
          calls costs one transfer, not one per call.

The snapshot is taken with SQLite's own backup API on the remote side, not
by copying the file: a plain copy of a database that is being written to can
be torn mid-page. `python3` is used for that rather than the `sqlite3` CLI
because Amazon Linux has the former for certain and the latter only maybe.

Only `ssh`/`scp` are invoked, against a host alias the user configured in
~/.ssh/config — no key paths, no passwords, nothing here to leak.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import time
import uuid
from pathlib import Path

from . import config


class SnapshotError(RuntimeError):
    """SSH/scp failed. The message is safe to show the agent."""


_REMOTE_BACKUP = (
    "import sqlite3,sys; src=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True); "
    "dst=sqlite3.connect(sys.argv[2]); src.backup(dst); dst.close(); src.close()"
)


def source_description() -> str:
    if not config.DB_SSH:
        return "local"
    age = snapshot_age()
    return f"snapshot of {config.DB_SSH}" + (f", {int(age)}s old" if age is not None else ", not yet fetched")


def snapshot_age() -> float | None:
    p = config.DB_PATH
    if not p.is_file():
        return None
    return time.time() - p.stat().st_mtime


def _run(cmd: list[str], *, timeout: int) -> None:
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=timeout)
    except subprocess.CalledProcessError as e:
        tail = (e.stderr or e.stdout or "").strip().splitlines()[-1:] or ["no output"]
        raise SnapshotError(f"{cmd[0]} to {config.DB_SSH.split(':', 1)[0]} failed: {tail[0]}") from e
    except subprocess.TimeoutExpired as e:
        raise SnapshotError(f"{cmd[0]} timed out after {timeout}s") from e
    except FileNotFoundError as e:
        raise SnapshotError(f"{cmd[0]} is not installed on this machine") from e


def fetch_snapshot() -> Path:
    """Take a fresh consistent snapshot of the remote database. Returns the
    local path. Raises SnapshotError with a readable reason."""
    host, _, remote = config.DB_SSH.partition(":")
    if not host or not remote:
        raise SnapshotError("HORIZON_DB_SSH must look like host:/path/to/market.db")

    local = config.DB_PATH
    local.parent.mkdir(parents=True, exist_ok=True)
    tag = uuid.uuid4().hex[:12]
    remote_tmp = f"/tmp/horizon-snapshot-{tag}.db"
    local_tmp = local.with_suffix(f".{tag}.part")

    try:
        _run(["ssh", "-o", "BatchMode=yes", host,
              f"python3 -c {shlex.quote(_REMOTE_BACKUP)} {shlex.quote(remote)} {shlex.quote(remote_tmp)}"],
             timeout=90)
        _run(["scp", "-q", "-o", "BatchMode=yes", f"{host}:{remote_tmp}", str(local_tmp)], timeout=300)
        os.replace(local_tmp, local)     # atomic: readers never see a half-written file
    finally:
        subprocess.run(["ssh", "-o", "BatchMode=yes", host, f"rm -f {shlex.quote(remote_tmp)}"],
                       capture_output=True, timeout=30)
        if local_tmp.exists():
            local_tmp.unlink()
    return local


def ensure_db(refresh: bool = False) -> Path:
    """The path every tool should open. Fetches a snapshot if remote and
    stale (or `refresh`), otherwise returns the path as configured."""
    if not config.DB_SSH:
        return config.DB_PATH
    age = snapshot_age()
    if refresh or age is None or age > config.SNAPSHOT_MAX_AGE:
        return fetch_snapshot()
    return config.DB_PATH
