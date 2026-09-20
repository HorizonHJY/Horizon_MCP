"""db_status — is the database there, and roughly what is in it.

The cheapest possible tool. It exists so the whole chain (WhatsApp → OpenClaw →
this server → SQLite → back) can be proven with a call that cannot go wrong
before anyone trusts an export.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .. import config, db


def db_status(*, db_path: Path | None = None) -> dict:
    path = db_path or config.DB_PATH
    if not path.is_file():
        return {"ok": False, "path": str(path), "error": "database file not found"}

    stat = path.stat()
    with db.connect(path) as conn:
        tables = db.list_tables(conn)

    return {
        "ok": True,
        "path": str(path),
        "bytes": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(timespec="seconds"),
        "tables": len(tables),
        "rows_total": sum(t.rows for t in tables),
        "export_dir": str(config.EXPORT_DIR),
        "export_max_rows": config.EXPORT_MAX_ROWS,
    }
