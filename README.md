# Horizon MCP

Tools an agent can call about the [Arch Bay](https://horizonyhj.com) site.
Runs next to OpenClaw over **stdio** — no port, no TLS, nothing reachable
from outside — and reads the site database **read-only**.

It runs in either of two places with the same code:

```
Mac mini (today)   WhatsApp → OpenClaw ─stdio─▶ horizon-mcp ─ssh snapshot─▶ EC2: market.db
EC2 box (later)    WhatsApp → OpenClaw ─stdio─▶ horizon-mcp ─local file────▶ market.db
```

Which one is decided by a single variable: set `HORIZON_DB_SSH` and the data
comes over SSH as a consistent snapshot (SQLite backup API, cached five
minutes); leave it unset and `HORIZON_DB_PATH` is the live file.

## Install

**Follow [INSTALL.md](INSTALL.md).** It is written for the agent doing the
install on the Mac mini, with a check after every step and a WhatsApp
acceptance test at the end. The EC2-local variant is the same steps with
block B of `.env.example` and no SSH.

## Tools

| Tool | What it does |
|---|---|
| `db_status()` | Where the data comes from (local, or a snapshot and its age), size, tables, rows, export dir. Call this first. |
| `list_tables()` | Exportable tables with row counts and the column a date range filters on. |
| `export_data(table, format="csv", since=None, until=None, limit=None)` | Writes one table to `HORIZON_EXPORT_DIR`; returns path, rows, bytes, `truncated`. Newest first. `format` is `csv` or `json`; `since`/`until` are ISO dates. |
| `refresh_data()` | Pull a fresh snapshot now, ignoring the cache. No-op when local. |

**Never exported, no override:** `user` (plaintext passwords, emails, contact
details) and `session` (live tokens). Every connection is `mode=ro`, so a
tool cannot write even by mistake. Refusals come back with the reason, so
the agent reads *'user' is never exported: it holds credentials* rather
than an opaque error.

## Deploy (every time after the first)

```bash
bash scripts/deploy.sh
```

Pull, ssh check (remote mode), read-only smoke test. stdio has no service
to restart.

## Develop

```bash
python3.11 -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest                          # throwaway db + fake ssh; includes a real stdio handshake
python -m horizon_mcp           # starts the server on stdio
```

Add a tool: one module in `horizon_mcp/tools/`, plain functions with no MCP
import so `pytest` can hit them; register in `server.py` with `@mcp.tool()`
and route anticipated failures through `ToolError` so the agent can read
them. The docstring is what the agent reads to decide when to call it —
write it for the agent.

## Config

All from the environment; `.env` is loaded if present and never overrides a
set variable. See `.env.example`. No secrets live in the repo: SSH goes
through a host alias in `~/.ssh/config`, so no key path or password is ever
configured here.

## When a tool needs to be remote

Not now. If one does: switch `main()` to `mcp.run(transport="streamable-http")`,
bind `127.0.0.1`, put it behind nginx + Let's Encrypt, and add a bearer-token
check before the first request is served. That is the order.
