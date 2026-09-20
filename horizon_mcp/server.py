"""The MCP server. Registers the tools and speaks stdio.

Run it directly to check it starts:

    python -m horizon_mcp

OpenClaw launches it the same way as a subprocess (see openclaw.example.json),
so there is no port, no TLS and nothing to expose. If a future tool genuinely
needs remote access, that is the moment to switch `main()` to
`mcp.run(transport="streamable-http")`, bind it to 127.0.0.1, put it behind
nginx and add a token check — not before.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import db, snapshot
from .tools.export import export_table
from .tools.status import db_status as _db_status

mcp = MCPServer(
    "horizon",
    instructions=(
        "Tools for the Arch Bay server. The database is opened read-only; the "
        "`user` and `session` tables are never exported. Call list_tables "
        "before export_data if you are unsure of a table name. When the data "
        "comes from a snapshot, db_status says how old it is; call "
        "refresh_data if the user wants the very latest."
    ),
)

# Failures the agent can act on go back as text. Anything else stays a crash:
# the SDK hides the traceback from the model and logs it, which is right.
_ANTICIPATED = (db.DeniedTable, db.UnknownTable, snapshot.SnapshotError, ValueError, FileNotFoundError)


@mcp.tool()
def db_status() -> dict:
    """Check the site database is reachable and summarise it: where it comes
    from (local file, or a snapshot pulled over SSH and how old), file size,
    table count, total rows, and where exports will go. Use this first to
    prove the connection works."""
    try:
        return _db_status()
    except _ANTICIPATED as e:
        raise ToolError(str(e)) from e


@mcp.tool()
def list_tables() -> list[dict]:
    """Every exportable table with its row count and, where it has one, the
    column a date range would filter on. Credential tables are omitted."""
    try:
        with db.connect(snapshot.ensure_db()) as conn:
            return [
                {"table": t.name, "rows": t.rows, "time_column": t.time_column}
                for t in db.list_tables(conn)
            ]
    except _ANTICIPATED as e:
        raise ToolError(str(e)) from e


@mcp.tool()
def export_data(
    table: str,
    format: str = "csv",
    since: str | None = None,
    until: str | None = None,
    limit: int | None = None,
) -> dict:
    """Export one table to a file and return its path for sending on.

    Args:
        table:  a table name from list_tables (case-insensitive).
        format: "csv" (default) or "json".
        since:  optional ISO date/datetime, e.g. "2026-09-01"; rows at or after it.
        until:  optional ISO date/datetime; rows at or before it.
        limit:  max rows, capped by the server's HORIZON_EXPORT_MAX_ROWS.

    Rows come newest first. The response includes `rows`, `bytes` and a
    `truncated` flag — tell the user those before sending a large file.
    The `user` and `session` tables are refused.
    """
    try:
        return export_table(table, format, since, until, limit)
    except _ANTICIPATED as e:
        raise ToolError(str(e)) from e


@mcp.tool()
def refresh_data() -> dict:
    """Pull a fresh snapshot of the database from the server right now,
    ignoring the cached one. Only meaningful when the data comes over SSH;
    on the server itself it is a no-op. Use when the user asks for the
    latest numbers."""
    try:
        path = snapshot.ensure_db(refresh=True)
    except _ANTICIPATED as e:
        raise ToolError(str(e)) from e
    return {"ok": True, "source": snapshot.source_description(), "path": str(path)}


def main() -> None:
    mcp.run()   # stdio


if __name__ == "__main__":
    main()
