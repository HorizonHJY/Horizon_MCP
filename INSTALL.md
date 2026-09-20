# Installing Horizon MCP on the Mac mini

Instructions for the agent doing the install. You are on the **Mac mini**
that runs OpenClaw (macOS, user `horizon`, home `/Users/horizon`). The site
and its database live on a different machine, the EC2 box, and this server
reaches them **over SSH** — nothing runs on the EC2 box, nothing changes
there.

Do every step in order and **stop at any check that fails** — report what you
saw rather than working around it.

## What you are installing

An MCP server with four tools — `db_status`, `list_tables`, `export_data`,
`refresh_data` — that OpenClaw launches as a **stdio subprocess**. When a tool
needs data it pulls a read-only **snapshot** of the site database from the
EC2 box over SSH (SQLite's own backup API, so it is consistent), caches it
for five minutes, and reads that. No port is opened, no service is created.

```
WhatsApp → OpenClaw ──(stdio)──▶ horizon-mcp ──(ssh, read-only snapshot)──▶ EC2: market.db
                ◀──── file path ───────┘
```

## Step 0 — The SSH key (the owner does this part, not you)

The owner will place the EC2 key on this Mac by hand. **Do not go looking for
it, generate one, or ask for its contents.** When they say it is in place,
confirm:

```bash
cat ~/.ssh/config
```

**Check:** there is a block like

```
Host archbay
    HostName 34.201.2.158
    User ec2-user
    IdentityFile ~/.ssh/archbay.pem
```

If there is no such block but the key file exists, create the block exactly as
above (with the real filename) and `chmod 600 ~/.ssh/archbay.pem`. Then:

```bash
ssh -o BatchMode=yes -o ConnectTimeout=10 archbay 'hostname && ls -la /home/ec2-user/Horisation/_data/market.db'
```

**Check:** it prints the EC2 hostname and the database file's size — with no
password prompt. If it asks for a password, the key is wrong; if it times out,
the EC2 security group does not allow this Mac's IP on port 22. Either way
stop and report; both are the owner's to fix.

## Step 1 — Python ≥ 3.10

This Mac's `python3` is 3.9, which is below what the MCP SDK needs.

```bash
brew install python@3.11
python3.11 --version
```

**Check:** prints `Python 3.11.x`. If `brew` is not installed, stop and
report — do not install Homebrew yourself.

## Step 2 — Clone

```bash
cd /Users/horizon
git clone https://github.com/HorizonHJY/Horizon_MCP.git
cd Horizon_MCP
```

**Check:** `ls` shows `horizon_mcp/`, `scripts/`, `tests/`, `pyproject.toml`.

## Step 3 — Config

```bash
cp .env.example .env
mkdir -p /Users/horizon/horizon-exports
```

`.env.example` already has the Mac layout as block **A** and it is correct
for this machine. Confirm these are the active (uncommented) lines:

```
HORIZON_DB_SSH=archbay:/home/ec2-user/Horisation/_data/market.db
HORIZON_DB_PATH=~/horizon-exports/market.snapshot.db
HORIZON_SNAPSHOT_MAX_AGE=300
HORIZON_EXPORT_DIR=~/horizon-exports
HORIZON_EXPORT_MAX_ROWS=5000
```

**Check:** block B's `HORIZON_DB_PATH=/home/ec2-user/...` line is still
commented out. (That path is for running on the EC2 box.)

## Step 4 — Install and smoke-test

```bash
bash scripts/deploy.sh
```

This picks `python3.11`, creates `.venv`, installs the pinned dependency
(`mcp>=2,<3`), checks `ssh archbay` answers, then pulls a real snapshot and
runs `db_status` on it — read-only throughout.

**Check:** the output includes

```
      ssh ok: ip-172-31-…
      db ok (snapshot of archbay:/home/ec2-user/Horisation/_data/market.db, 0s old): 25 tables, … rows, exports -> /Users/horizon/horizon-exports
```

and `ls -la ~/horizon-exports/market.snapshot.db` exists. Table and row
counts will differ; `ssh ok` and `db ok` are what matter.

## Step 5 — Run the test suite

```bash
.venv/bin/python -m pytest -q
```

**Check:** `16 passed`. These use a throwaway database and a fake `ssh`; they
prove the tools and the snapshot logic. `tests/test_stdio.py` launches the
real server over stdio and calls every tool — the same path OpenClaw will use.

## Step 6 — Register with OpenClaw

The entry is in `openclaw.example.json`:

```json
{
  "mcpServers": {
    "horizon": {
      "command": "/Users/horizon/Horizon_MCP/.venv/bin/python",
      "args": ["-m", "horizon_mcp"],
      "cwd": "/Users/horizon/Horizon_MCP",
      "env": {
        "HORIZON_DB_SSH": "archbay:/home/ec2-user/Horisation/_data/market.db",
        "HORIZON_DB_PATH": "/Users/horizon/horizon-exports/market.snapshot.db",
        "HORIZON_SNAPSHOT_MAX_AGE": "300",
        "HORIZON_EXPORT_DIR": "/Users/horizon/horizon-exports",
        "HORIZON_EXPORT_MAX_ROWS": "5000",
        "HOME": "/Users/horizon"
      }
    }
  }
}
```

Put it wherever OpenClaw keeps its MCP server definitions. **The key name
`mcpServers` is the common convention, not a guarantee** — if OpenClaw's
config uses a different section name or shape for stdio servers, match
OpenClaw's, keeping `command`, `args`, `cwd` and `env` as above. `HOME` is
included so that `ssh` finds `~/.ssh/config` even if OpenClaw launches
subprocesses with a stripped environment. Restart OpenClaw so it reads the
config.

**Check:** OpenClaw lists a server named `horizon` with four tools.

## Step 7 — Prove the chain from WhatsApp

Send, in this order, and confirm each:

1. **"Check the database status"** → `db_status`; the reply says the source
   is a snapshot of `archbay:…`, how old, table count, row count. This proves
   the whole chain — WhatsApp, OpenClaw, this server, SSH, the EC2 box — with
   a call that cannot go wrong.
2. **"What tables can you export?"** → `list_tables`. `user` and `session`
   must **not** appear.
3. **"Export the listings table as CSV"** → `export_data`; the agent reports
   rows and size and sends the file. Open it: first line is the column
   headers, rows are newest first.
4. **"Export the user table"** → the agent must **refuse**, quoting
   `'user' is never exported: it holds credentials`. If it exports anything,
   stop and report — that is a bug, not a configuration issue.
5. **"Get the latest data"** → `refresh_data`; the reply's age resets to
   `0s old`.

## Updating later

```bash
bash /Users/horizon/Horizon_MCP/scripts/deploy.sh
```

That is a `git pull`, the ssh check, and the smoke test. stdio has no service
to restart; OpenClaw launches a fresh subprocess per tool call. If OpenClaw
turns out to keep the subprocess alive between calls, restart OpenClaw after
a deploy.

## Things you must not do

- Do not do anything on the EC2 box. This install is Mac-only; the only
  contact with the server is `ssh archbay` reading the database.
- Do not open a port, add nginx config, or create a launchd/systemd service.
  stdio needs none of them.
- Do not look for, copy, print or generate SSH keys. Step 0 is the owner's.
- Do not point `HORIZON_EXPORT_DIR` or `HORIZON_DB_PATH` inside any git
  checkout.
- Do not commit `.env`, the snapshot, or anything from `horizon-exports/` —
  all gitignored; keep them that way.
- Do not "fix" a refusal to export `user` or `session`. It is the point.
