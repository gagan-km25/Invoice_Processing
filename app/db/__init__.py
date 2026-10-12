"""SQLite access helpers.

Design rules (docs/02-exploration §7):
- Connections are short-lived — opened per operation, closed immediately.
  The project folder is OneDrive-synced; long-held locks can corrupt the
  database file (risk T-3).
- `PRAGMA foreign_keys = ON` is set on every connection (SQLite defaults it
  OFF per connection); cascading deletes depend on it.
- All SQL lives in repository.py and migrations.py; nothing else writes SQL.

Schema versioning (Sprint E0): fresh databases are created from schema.sql
and stamped `PRAGMA user_version = 2`; v1 databases are upgraded by
migrations.migrate_v1_to_v2 (table rebuild inside one transaction, followed
by a foreign_key_check gate). The live database is never migrated before a
copied-database rehearsal has passed and been recorded.
"""
import sqlite3

from flask import current_app

from app.db import migrations
from app.db.migrations import CURRENT_SCHEMA_VERSION


def get_db() -> sqlite3.Connection:
    """Return a new short-lived connection with FK enforcement on."""
    conn = sqlite3.connect(current_app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(app) -> None:
    """Create or upgrade the schema, then stamp the schema version.

    - No invoices table → fresh database: apply schema.sql (v2 DDL).
    - v1 shape (has invoices, no v2 columns) → run migrate_v1_to_v2.
    - v2 shape → re-assert schema.sql idempotently (CREATE IF NOT EXISTS
      no-ops) and stamp the version if it was missing.
    Anything else (version claims ≥2 but shape is not v2) is a hard error —
    an unrecognised database must never be silently "upgraded".
    """
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.isolation_level = None  # explicit transaction control (migrations)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        has_invoices = migrations._table_exists(conn, "invoices")

        if not has_invoices:
            conn.executescript(app.config["SCHEMA"].read_text(encoding="utf-8"))
            conn.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")
        elif migrations.is_v2_shape(conn):
            conn.executescript(app.config["SCHEMA"].read_text(encoding="utf-8"))
            if version < CURRENT_SCHEMA_VERSION:
                conn.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")
        elif version < CURRENT_SCHEMA_VERSION:
            migrations.migrate_v1_to_v2(conn)
        else:
            raise RuntimeError(
                "database claims a current schema version but does not have "
                "the v2 shape — refusing to touch it"
            )
    finally:
        conn.close()
