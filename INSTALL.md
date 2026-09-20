# Installing Horizon MCP on the Arch Bay server

Instructions for the agent doing the install. You are on the EC2 box that
already runs the site (`/home/ec2-user/Horisation`) and OpenClaw. Do every
step in order and **stop at any check that fails** — report what you saw
rather than working around it.

Nothing here touches the site, its service, nginx, or the database contents.
The database is only ever opened read-only.

## What you are installing

An MCP server with three tools — `db_status`, `list_tables`, `export_data` —
that OpenClaw launches as a **stdio subprocess**. No port is opened, no
service is created, nothing is exposed to the internet.

```
WhatsApp → OpenClaw ──(stdio)──▶ horizon-mcp ──(read-only)──▶ market.db
                ◀──── file path ───────┘
```

## Step 1 — Clone

```bash
cd /home/ec2-user
git clone https://github.com/HorizonHJY/Horizon_MCP.git
cd Horizon_MCP
```

**Check:** `ls` shows `horizon_mcp/`, `scripts/`, `tests/`, `pyproject.toml`.

## Step 2 — Config

```bash
cp .env.example .env
mkdir -p /home/ec2-user/horizon-exports
```

Open `.env` and confirm the three values. The defaults are correct for this
server; change them only if a path differs:

```
HORIZON_DB_PATH=/home/ec2-user/Horisation/_data/market.db
HORIZON_EXPORT_DIR=/home/ec2-user/horizon-exports
HORIZON_EXPORT_MAX_ROWS=5000
```

**Check:** `ls -la /home/ec2-user/Horisation/_data/market.db` exists and is
readable by the user OpenClaw runs as. If OpenClaw runs as a different user
than `ec2-user`, that user needs read on the db and write on the export dir.

## Step 3 — Install and smoke-test

```bash
bash scripts/deploy.sh
```

This creates `.venv`, installs the pinned dependency (`mcp>=2,<3`), and runs
a **read-only** `db_status` against the real database.

**Check:** the output ends with a line like

```
      db ok: 25 tables, 1234 rows, exports -> /home/ec2-user/horizon-exports
Done.
```

If it says `python3.11: command not found`, the script falls back to
`python3`; that is fine as long as it is ≥ 3.10 (`python3 --version`).

## Step 4 — Run the test suite

```bash
.venv/bin/python -m pytest -q
```

**Check:** `10 passed`. This includes `tests/test_stdio.py`, which launches
the real server over stdio and calls every tool — the same path OpenClaw
will use. If this passes, the server works; anything after this is OpenClaw
configuration.

## Step 5 — Register with OpenClaw

The entry is in `openclaw.example.json`:

```json
{
  "mcpServers": {
    "horizon": {
      "command": "/home/ec2-user/Horizon_MCP/.venv/bin/python",
      "args": ["-m", "horizon_mcp"],
      "cwd": "/home/ec2-user/Horizon_MCP",
      "env": {
        "HORIZON_DB_PATH": "/home/ec2-user/Horisation/_data/market.db",
        "HORIZON_EXPORT_DIR": "/home/ec2-user/horizon-exports",
        "HORIZON_EXPORT_MAX_ROWS": "5000"
      }
    }
  }
}
```

Put it wherever OpenClaw keeps its MCP server definitions. **The key name
`mcpServers` is the common convention, not a guarantee** — if OpenClaw's
config uses a different section name or shape for stdio servers, match
OpenClaw's, keeping `command`, `args`, `cwd` and `env` as above. Then restart
OpenClaw so it reads the config.

**Check:** OpenClaw lists a server named `horizon` with three tools.

## Step 6 — Prove the chain from WhatsApp

Send, in this order, and confirm each:

1. **"Check the database status"** → the agent calls `db_status` and reports
   table count, row count and the export directory. This proves the whole
   chain with a call that cannot go wrong.
2. **"What tables can you export?"** → `list_tables`. `user` and `session`
   must **not** appear.
3. **"Export the listings table as CSV"** → `export_data`; the agent reports
   rows and size and sends the file. Open it: first line is the column
   headers, rows are newest first.
4. **"Export the user table"** → the agent must **refuse**, quoting
   `'user' is never exported: it holds credentials`. If it exports anything,
   stop and report — that is a bug, not a configuration issue.

## Updating later

```bash
bash /home/ec2-user/Horizon_MCP/scripts/deploy.sh
```

That is a `git pull` plus the smoke test. stdio has no service to restart;
OpenClaw launches a fresh subprocess per tool call. If OpenClaw turns out to
keep the subprocess alive between calls, restart OpenClaw after a deploy —
and uncomment the last line of `scripts/deploy.sh` with its service name.

## Things you must not do

- Do not open a port, add an nginx `location`, or create a systemd unit for
  this. stdio needs none of them, and the moment it is reachable over HTTP
  it becomes a remote-execution endpoint that needs auth it does not have.
- Do not point `HORIZON_EXPORT_DIR` inside any git checkout.
- Do not commit `.env` or anything from `horizon-exports/` — both are
  gitignored; keep them that way.
- Do not "fix" a refusal to export `user` or `session`. It is the point.
