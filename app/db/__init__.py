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
    """Apply the schema (idempotent) and migrate, if needed, then close.

    Migration: columns introduced after Sprint 0 are added to existing
    databases via ALTER TABLE — CREATE TABLE IF NOT EXISTS alone would leave
    older files without them. Constants only; never user input.
    """
    conn = sqlite3.connect(app.config["DATABASE"])
    try:
        conn.executescript(app.config["SCHEMA"].read_text(encoding="utf-8"))
        existing = {row[1] for row in conn.execute("PRAGMA table_info(invoices)")}
        for column, decl in (
            ("vendor_tax_id", "TEXT"),
            ("bill_to", "TEXT"),
            ("discount", "REAL"),
        ):
            if column not in existing:
                conn.execute(f"ALTER TABLE invoices ADD COLUMN {column} {decl}")
        conn.commit()
    finally:
        conn.close()
