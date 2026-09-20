"""Drive the real server over stdio the way OpenClaw will.

This is the test that matters: the unit tests prove the tools, this proves
the server starts, announces them, and answers. It caught the mcp 2.x rename
of FastMCP the first time it ran.
"""

import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO = Path(__file__).resolve().parent.parent


def _result(res):
    """A tool's result, the way a client has to read it under mcp 2.x: a
    `-> dict` return arrives only as JSON text, a `-> list[...]` return also
    arrives as structured_content wrapped in {"result": [...]}."""
    sc = res.structured_content
    if isinstance(sc, dict) and set(sc) == {"result"}:
        return sc["result"]
    if sc is not None:
        return sc
    return json.loads(res.content[0].text)


@pytest.fixture
def params(tmp_path: Path) -> StdioServerParameters:
    dbp = tmp_path / "market.db"
    conn = sqlite3.connect(dbp)
    conn.executescript(
        """
        CREATE TABLE user (id INTEGER PRIMARY KEY, username TEXT, password TEXT);
        INSERT INTO user VALUES (1, 'horizon', 'SECRET-PASSWORD');
        CREATE TABLE listings (id INTEGER PRIMARY KEY, title TEXT, created_at TEXT);
        INSERT INTO listings VALUES (1, 'Chair', '2026-08-01'), (2, 'Bike 单车', '2026-09-05');
        """
    )
    conn.commit()
    conn.close()
    env = dict(
        os.environ,
        HORIZON_DB_PATH=str(dbp),
        HORIZON_EXPORT_DIR=str(tmp_path / "out"),
        HORIZON_EXPORT_MAX_ROWS="100",
    )
    return StdioServerParameters(command=sys.executable, args=["-m", "horizon_mcp"], env=env, cwd=str(REPO))


def test_full_chain_over_stdio(params):
    async def run():
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                init = await s.initialize()
                assert init.server_info.name == "horizon"

                tools = {t.name for t in (await s.list_tools()).tools}
                assert tools == {"db_status", "list_tables", "export_data"}

                st = _result(await s.call_tool("db_status", {}))
                assert st["ok"] and st["tables"] == 1     # `user` not counted

                lt = _result(await s.call_tool("list_tables", {}))
                assert [t["table"] for t in lt] == ["listings"]

                ex = _result(await s.call_tool(
                    "export_data", {"table": "listings", "format": "json", "since": "2026-09-01"}))
                assert ex["rows"] == 1 and not ex["truncated"]
                data = json.loads(Path(ex["path"]).read_text(encoding="utf-8"))
                assert [d["title"] for d in data] == ["Bike 单车"]

                # Refused, with a reason the agent can read, and nothing leaked.
                denied = await s.call_tool("export_data", {"table": "user"})
                assert denied.is_error
                msg = denied.content[0].text
                assert "never exported" in msg and "SECRET" not in msg

                unknown = await s.call_tool("export_data", {"table": "nope"})
                assert unknown.is_error and "list_tables" in unknown.content[0].text

    asyncio.run(run())
