"""export_data — pull a table out of the site database into a file.

The file is the product: OpenClaw picks it up from the returned path and sends
it on over WhatsApp. Nothing is hosted, nothing stays open.
"""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .. import config, db, snapshot

FORMATS = ("csv", "json")
_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def export_table(
    table: str,
    fmt: str = "csv",
    since: str | None = None,
    until: str | None = None,
    limit: int | None = None,
    *,
    db_path: Path | None = None,
    export_dir: Path | None = None,
) -> dict:
    """Write `table` to a file and describe what was written.

    Returns a dict rather than the contents: a table can be thousands of rows,
    and the agent only needs the path and the numbers to tell the user what
    it is about to send.
    """
    fmt = (fmt or "csv").lower()
    if fmt not in FORMATS:
        raise ValueError(f"format must be one of {', '.join(FORMATS)}")

    cap = config.EXPORT_MAX_ROWS
    n = cap if limit is None else max(1, min(int(limit), cap))

    with db.connect(db_path or snapshot.ensure_db()) as conn:
        name = db.resolve_table(conn, table)
        columns, rows = db.fetch_rows(conn, name, since=since, until=until, limit=n)

    out_dir = export_dir or config.EXPORT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{_SAFE.sub('_', name)}_{_stamp()}.{fmt}"

    if fmt == "csv":
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(columns)
            w.writerows(tuple(r) for r in rows)
    else:
        with path.open("w", encoding="utf-8") as f:
            json.dump([dict(zip(columns, r)) for r in rows], f, ensure_ascii=False, indent=2)

    return {
        "table": name,
        "format": fmt,
        "rows": len(rows),
        "truncated": len(rows) >= n,   # hit the cap — there may be more
        "columns": columns,
        "since": since,
        "until": until,
        "path": str(path),
        "bytes": path.stat().st_size,
    }
