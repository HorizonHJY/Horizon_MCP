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

from . import config, db
from .tools.export import export_table
from .tools.status import db_status as _db_status

mcp = MCPServer(
    "horizon",
    instructions=(
        "Tools for the Arch Bay server. The database is opened read-only; the "
        "`user` and `session` tables are never exported. Call list_tables "
        "before export_data if you are unsure of a table name."
    ),
)


@mcp.tool()
def db_status() -> dict:
    """Check the site database is reachable and summarise it: file size,
    last modified, table count, total rows, and where exports will go.
    Use this first to prove the connection works."""
    return _db_status()


@mcp.tool()
def list_tables() -> list[dict]:
    """Every exportable table with its row count and, where it has one, the
    column a date range would filter on. Credential tables are omitted."""
    try:
        with db.connect(config.DB_PATH) as conn:
            return [
                {"table": t.name, "rows": t.rows, "time_column": t.time_column}
                for t in db.list_tables(conn)
            ]
    except FileNotFoundError as e:
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
    # Anticipated failures go back to the agent as text it can act on. Anything
    # else is a crash and stays a crash: the SDK hides the traceback from the
    # model and logs it, which is right — a stack trace is not an answer.
    try:
        return export_table(table, format, since, until, limit)
    except (db.DeniedTable, db.UnknownTable, ValueError, FileNotFoundError) as e:
        raise ToolError(str(e)) from e


def main() -> None:
    mcp.run()   # stdio


if __name__ == "__main__":
    main()
