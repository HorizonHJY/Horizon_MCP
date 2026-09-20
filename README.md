# Horizon MCP

Tools an agent can call against the [Arch Bay](https://horizonyhj.com) server.
Runs **on the same EC2 box** as the site and as OpenClaw, over **stdio** — no
port, no TLS, nothing reachable from outside.

```
WhatsApp → OpenClaw ──(stdio subprocess)──▶ horizon-mcp ──(read-only)──▶ market.db
                ◀────────── file path ─────────────┘
```

## Tools

| Tool | What it does |
|---|---|
| `db_status()` | Is the database there, how big, how many tables/rows, where exports go. Call this first. |
| `list_tables()` | Exportable tables with row counts and the column a date range filters on. |
| `export_data(table, format="csv", since=None, until=None, limit=None)` | Writes one table to `HORIZON_EXPORT_DIR` and returns the path, row count and size. Newest first. `format` is `csv` or `json`; `since`/`until` are ISO dates. |

**Never exported, no override:** `user` (plaintext passwords, emails, contact
details) and `session` (live tokens). The database is opened `mode=ro`, so a
tool cannot write to it even by mistake.

## Deploy (first time, on the server)

```bash
cd /home/ec2-user
git clone https://github.com/HorizonHJY/Horizon_MCP.git
cd Horizon_MCP
cp .env.example .env            # edit if the paths differ
mkdir -p /home/ec2-user/horizon-exports
bash scripts/deploy.sh          # venv, deps, read-only smoke test against the real db
```

Then point OpenClaw at it — `openclaw.example.json` has the entry (adjust the
key name to whatever OpenClaw's MCP config calls it). Prove the chain with
`db_status` from WhatsApp before trusting an export.

## Deploy (every time after)

```bash
bash /home/ec2-user/Horizon_MCP/scripts/deploy.sh
```

That is a `git pull` plus the smoke test. stdio has no service to restart;
OpenClaw starts a fresh subprocess per call.

## Develop

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest                                            # runs against a throwaway db
python -m horizon_mcp                             # starts the server on stdio
```

Add a tool: one module in `horizon_mcp/tools/`, plain functions with no MCP
import so `pytest` can hit them; register it in `server.py` with `@mcp.tool()`.
The docstring is what the agent reads to decide when to call it — write it for
the agent, not for the reader of the code.

## Config

All from the environment (`.env` is loaded if present and never overrides a
set variable). See `.env.example`. Nothing secret lives in the repo: the
database path is not a secret, and the tools hold no credentials of their own.

## When a tool needs to be remote

Not now. If one does: switch `main()` to `mcp.run(transport="streamable-http")`,
bind `127.0.0.1`, put it behind the existing nginx + Let's Encrypt, and add a
bearer-token check before the first request is served. That is the order.
