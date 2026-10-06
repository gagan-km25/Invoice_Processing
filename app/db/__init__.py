"""SQLite access helpers.

Design rules (docs/02-exploration §7):
- Connections are short-lived — opened per operation, closed immediately.
  The project folder is OneDrive-synced; long-held locks can corrupt the
  database file (risk T-3).
- `PRAGMA foreign_keys = ON` is set on every connection (SQLite defaults it
  OFF per connection); cascading deletes depend on it.
- All SQL lives in repository.py (from Sprint 1); nothing else writes SQL.
"""
import sqlite3

from flask import current_app


def get_db() -> sqlite3.Connection:
    """Return a new short-lived connection with FK enforcement on."""
    conn = sqlite3.connect(current_app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(app) -> None:
    """Apply the schema (idempotent) to the configured database."""
    conn = sqlite3.connect(app.config["DATABASE"])
    try:
        conn.executescript(app.config["SCHEMA"].read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()
