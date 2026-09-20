"""Tests run against a throwaway SQLite file, never the real database."""

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from horizon_mcp import db
from horizon_mcp.tools.export import export_table
from horizon_mcp.tools.status import db_status


@pytest.fixture
def fake_db(tmp_path: Path) -> Path:
    path = tmp_path / "market.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE user (id INTEGER PRIMARY KEY, username TEXT, password TEXT);
        INSERT INTO user VALUES (1, 'horizon', 'plaintext-secret');

        CREATE TABLE session (id INTEGER PRIMARY KEY, token TEXT, created_at TEXT);
        INSERT INTO session VALUES (1, 'tok', '2026-09-01');

        CREATE TABLE listings (id INTEGER PRIMARY KEY, title TEXT, price REAL, created_at TEXT);
        INSERT INTO listings VALUES
          (1, 'Chair', 35, '2026-08-01T10:00:00'),
          (2, 'Bike',  320, '2026-09-05T10:00:00'),
          (3, 'Desk 桌子', 110, '2026-09-12T10:00:00');

        CREATE TABLE categories (slug TEXT PRIMARY KEY, label TEXT);
        INSERT INTO categories VALUES ('furniture', 'Furniture');
        """
    )
    conn.commit()
    conn.close()
    return path


def test_credential_tables_are_refused(fake_db, tmp_path):
    for t in ("user", "USER", "session"):
        with pytest.raises(db.DeniedTable):
            export_table(t, db_path=fake_db, export_dir=tmp_path)
    # and they never appear in the listing either
    with db.connect(fake_db) as conn:
        assert {t.name for t in db.list_tables(conn)} == {"listings", "categories"}


def test_unknown_table(fake_db, tmp_path):
    with pytest.raises(db.UnknownTable):
        export_table("nope", db_path=fake_db, export_dir=tmp_path)


def test_csv_export_newest_first(fake_db, tmp_path):
    out = export_table("listings", "csv", db_path=fake_db, export_dir=tmp_path)
    assert out["rows"] == 3 and out["format"] == "csv" and out["truncated"] is False
    with open(out["path"], newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["id", "title", "price", "created_at"]
    assert [r[1] for r in rows[1:]] == ["Desk 桌子", "Bike", "Chair"]   # newest first, utf-8 intact


def test_json_export_and_date_range(fake_db, tmp_path):
    out = export_table("listings", "json", since="2026-09-01", db_path=fake_db, export_dir=tmp_path)
    data = json.loads(Path(out["path"]).read_text(encoding="utf-8"))
    assert [d["title"] for d in data] == ["Desk 桌子", "Bike"]
    out2 = export_table("listings", "json", since="2026-09-01", until="2026-09-06",
                        db_path=fake_db, export_dir=tmp_path)
    assert out2["rows"] == 1


def test_date_range_on_table_without_time_column(fake_db, tmp_path):
    with pytest.raises(ValueError):
        export_table("categories", since="2026-01-01", db_path=fake_db, export_dir=tmp_path)


def test_limit_and_truncated_flag(fake_db, tmp_path):
    out = export_table("listings", limit=2, db_path=fake_db, export_dir=tmp_path)
    assert out["rows"] == 2 and out["truncated"] is True


def test_database_is_opened_read_only(fake_db):
    with db.connect(fake_db) as conn:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM listings")


def test_status(fake_db):
    s = db_status(db_path=fake_db)
    assert s["ok"] and s["tables"] == 2 and s["rows_total"] == 4


def test_status_missing_db(tmp_path):
    s = db_status(db_path=tmp_path / "missing.db")
    assert s["ok"] is False
