"""The remote path, with ssh/scp replaced by a fake that records what was
asked and produces a real SQLite file where scp would have put one."""

import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

import pytest

from horizon_mcp import config, snapshot


@pytest.fixture
def remote_db(tmp_path: Path) -> Path:
    src = tmp_path / "remote-market.db"
    conn = sqlite3.connect(src)
    conn.executescript("CREATE TABLE listings (id INTEGER PRIMARY KEY, title TEXT); INSERT INTO listings VALUES (1,'Chair');")
    conn.commit()
    conn.close()
    return src


@pytest.fixture
def fake_ssh(monkeypatch, remote_db):
    """Stand-in for subprocess.run. `ssh … python3 -c …` is accepted as the
    backup step; `scp host:remote local` copies remote_db to `local`."""
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        if cmd[0] == "scp":
            shutil.copy(remote_db, cmd[-1])
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    return calls


@pytest.fixture
def remote_mode(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DB_SSH", "archbay:/home/ec2-user/Horisation/_data/market.db")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "cache" / "market.snapshot.db")
    monkeypatch.setattr(config, "SNAPSHOT_MAX_AGE", 300)


def test_local_mode_is_a_passthrough(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DB_SSH", "")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "market.db")
    assert snapshot.ensure_db() == tmp_path / "market.db"
    assert snapshot.source_description() == "local"


def test_first_call_fetches_then_reuses(remote_mode, fake_ssh):
    p = snapshot.ensure_db()
    assert p.is_file()
    assert sqlite3.connect(p).execute("SELECT title FROM listings").fetchone()[0] == "Chair"

    # backup on the remote via python3, scp it down, clean up the remote temp
    kinds = [c[0] for c in fake_ssh]
    assert kinds == ["ssh", "scp", "ssh"]
    assert "python3 -c" in fake_ssh[0][-1] and "sqlite3 /" not in fake_ssh[0][-1]   # python API, not the sqlite3 CLI
    assert fake_ssh[1][-2].startswith("archbay:/tmp/horizon-snapshot-")
    assert fake_ssh[2][-1].startswith("rm -f /tmp/horizon-snapshot-")
    assert "s old" in snapshot.source_description()

    n = len(fake_ssh)
    snapshot.ensure_db()                # fresh enough: no transfer
    assert len(fake_ssh) == n


def test_stale_snapshot_is_refetched(remote_mode, fake_ssh):
    p = snapshot.ensure_db()
    old = time.time() - 3600
    import os
    os.utime(p, (old, old))
    n = len(fake_ssh)
    snapshot.ensure_db()
    assert len(fake_ssh) == n + 3


def test_refresh_forces_a_fetch(remote_mode, fake_ssh):
    snapshot.ensure_db()
    n = len(fake_ssh)
    snapshot.ensure_db(refresh=True)
    assert len(fake_ssh) == n + 3


def test_ssh_failure_is_readable_and_leaves_no_partial_file(remote_mode, monkeypatch, tmp_path):
    def run(cmd, **kw):
        if cmd[0] == "ssh" and "python3" in cmd[-1]:
            raise subprocess.CalledProcessError(255, cmd, stderr="ssh: Could not resolve hostname archbay")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(subprocess, "run", run)

    with pytest.raises(snapshot.SnapshotError) as e:
        snapshot.ensure_db()
    assert "archbay" in str(e.value) and "resolve hostname" in str(e.value)
    assert not list((tmp_path / "cache").glob("*.part")) if (tmp_path / "cache").exists() else True


def test_bad_ssh_setting(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DB_SSH", "archbay")          # no colon
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "x.db")
    with pytest.raises(snapshot.SnapshotError):
        snapshot.ensure_db()
