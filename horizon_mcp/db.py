"""Read-only access to the site database.

Every connection is opened with SQLite's `mode=ro` URI flag, so even a bug in
a tool cannot write. Table names are validated against `sqlite_master` and
never interpolated from user input without that check.

Two tables are refused outright and cannot be unlocked by any parameter:

    user      passwords are stored in plaintext (a known limitation of the
              site, see its CLAUDE.md) alongside emails and contact details
    session   live login tokens

An export tool that could hand either of those to a phone over WhatsApp would
be the single worst thing on the server. Everything else is the owner's own
data and is theirs to export.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

DENIED_TABLES = frozenset({"user", "session"})

# Columns to prefer when a caller asks for a date range. Checked in order;
# the first one the table actually has is used.
TIME_COLUMNS = ("created_at", "joined_at", "read_at", "time_start")


class DeniedTable(PermissionError):
    """The table exists but is never exportable."""


class UnknownTable(LookupError):
    """No such table."""


@dataclass(frozen=True)
class TableInfo:
    name: str
    rows: int
    time_column: str | None


def connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.is_file():
        raise FileNotFoundError(f"database not found at {db_path}")
    uri = f"file:{db_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _all_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [r["name"] for r in rows]


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    # `table` has already been validated against sqlite_master by the caller.
    return [r["name"] for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]


def resolve_table(conn: sqlite3.Connection, table: str) -> str:
    """Return the canonical table name, or raise. The only path to a name that
    is safe to place in SQL."""
    known = _all_tables(conn)
    for name in known:
        if name.lower() == table.strip().lower():
            if name in DENIED_TABLES:
                raise DeniedTable(f"'{name}' is never exported: it holds credentials")
            return name
    raise UnknownTable(f"no table called '{table}'. Try list_tables.")


def time_column_for(conn: sqlite3.Connection, table: str) -> str | None:
    cols = set(_columns(conn, table))
    for c in TIME_COLUMNS:
        if c in cols:
            return c
    return None


def list_tables(conn: sqlite3.Connection) -> list[TableInfo]:
    out = []
    for name in _all_tables(conn):
        if name in DENIED_TABLES:
            continue
        count = conn.execute(f'SELECT COUNT(*) AS n FROM "{name}"').fetchone()["n"]
        out.append(TableInfo(name=name, rows=count, time_column=time_column_for(conn, name)))
    return out


def fetch_rows(
    conn: sqlite3.Connection,
    table: str,
    *,
    since: str | None = None,
    until: str | None = None,
    limit: int,
) -> tuple[list[str], list[sqlite3.Row]]:
    """Rows from an already-resolved table, newest first when there is a time
    column, capped at `limit`. Dates are ISO strings compared textually, which
    is how the site stores them."""
    where, params = [], []
    tcol = time_column_for(conn, table)
    if since or until:
        if not tcol:
            raise ValueError(f"'{table}' has no time column, so a date range does not apply")
        if since:
            where.append(f'"{tcol}" >= ?')
            params.append(since)
        if until:
            where.append(f'"{tcol}" <= ?')
            params.append(until)
    sql = f'SELECT * FROM "{table}"'
    if where:
        sql += " WHERE " + " AND ".join(where)
    if tcol:
        sql += f' ORDER BY "{tcol}" DESC'
    sql += " LIMIT ?"
    params.append(limit)
    cur = conn.execute(sql, params)
    columns = [d[0] for d in cur.description]
    return columns, cur.fetchall()
