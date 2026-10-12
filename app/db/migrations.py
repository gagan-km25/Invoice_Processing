"""Versioned schema migrations for the enhancement assignment (Sprint E0).

Strategy (approved plan §D):
- Schema version tracked in `PRAGMA user_version` (fresh v2 databases are
  created by schema.sql and stamped directly).
- v1 → v2 follows the standard SQLite table-rebuild procedure
  (sqlite.org/lang_altertable.html): create `invoices_new` with the v2 DDL,
  INSERT..SELECT copy with status mapping, drop the old table, rename, then
  ALTER the lines table and create the new audit table + indexes. The whole
  rebuild runs in ONE transaction with foreign_keys OFF (a PRAGMA no-op
  inside a transaction), followed by `PRAGMA foreign_key_check` — a hard
  failure if any row did not survive intact.
- Status mapping (approved decision 5): 'extracted' → 'completed',
  'saved' → 'completed'; 'uploaded' and 'failed' keep their names. The
  original value is preserved in `legacy_status`, and each migrated invoice
  receives exactly one `record_migrated` audit row.

Safety rule: the live database is never migrated until this migration has
passed on a copy and the copied-database rehearsal is recorded (TC-MIG-08).
"""
import sqlite3
from datetime import datetime, timezone

CURRENT_SCHEMA_VERSION = 2

# Canonical lifecycle statuses (must match Config.INVOICE_STATUSES).
_CANONICAL_STATUSES = (
    "uploaded", "processing", "completed", "validation_failed",
    "pending_approval", "approved", "rejected", "failed",
)

# v2 DDL for the rebuild target. Column-for-column identical to schema.sql —
# TC-MIG-09 asserts a fresh v2 database and a migrated v1 database end up
# with the same shape, so any drift between the two fails a test.
_V2_INVOICES_NEW_DDL = """
CREATE TABLE invoices_new (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    file_hash         TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    stored_filename   TEXT NOT NULL,
    file_type         TEXT NOT NULL DEFAULT 'pdf',
    vendor            TEXT,
    vendor_tax_id     TEXT,
    invoice_number    TEXT,
    invoice_date      TEXT,
    due_date          TEXT,
    bill_to           TEXT,
    bill_to_address   TEXT,
    ship_to_name      TEXT,
    ship_to_address   TEXT,
    currency          TEXT,
    po_number         TEXT,
    subtotal          REAL,
    discount          REAL,
    tax               REAL,
    tax_rate          REAL,
    total             REAL,
    status            TEXT NOT NULL
                      CHECK (status IN (
                          'uploaded', 'processing', 'completed',
                          'validation_failed', 'pending_approval',
                          'approved', 'rejected', 'failed',
                          'extracted', 'saved')),
    legacy_status     TEXT,
    extraction_json   TEXT,
    raw_response      TEXT,
    validation_status TEXT,
    validation_json   TEXT,
    dup_status        TEXT,
    dup_matches       TEXT,
    approver_role     TEXT,
    rejection_reason  TEXT,
    acted_by          TEXT,
    acted_at          TEXT,
    extract_attempts  INTEGER NOT NULL DEFAULT 0,
    error_message     TEXT,
    page_count        INTEGER,
    created_at        TEXT,
    updated_at        TEXT
)
"""

_AUDIT_DDL = """
CREATE TABLE IF NOT EXISTS invoice_audit (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id  INTEGER NOT NULL
                REFERENCES invoices(id) ON DELETE CASCADE,
    event_type  TEXT NOT NULL,
    actor       TEXT NOT NULL DEFAULT 'system',
    details     TEXT,
    created_at  TEXT NOT NULL
)
"""


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def is_v2_shape(conn: sqlite3.Connection) -> bool:
    """True when the invoices table already carries v2 columns and the audit
    table exists (guards against re-migrating a database that predates its
    user_version stamp)."""
    return "po_number" in _columns(conn, "invoices") and _table_exists(
        conn, "invoice_audit"
    )


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Rebuild the v1 schema into v2, preserving every invoice and line.

    Idempotent via the caller: init_db only invokes this when the database
    has a v1 shape and user_version < CURRENT_SCHEMA_VERSION.
    """
    if _CANONICAL_STATUSES is None:  # pragma: no cover - constant guard
        raise RuntimeError("status list not loaded")

    conn.execute("PRAGMA foreign_keys = OFF")  # no-op inside a transaction
    try:
        conn.execute("BEGIN IMMEDIATE")

        # 1. Rebuild target with v2 DDL.
        conn.execute(_V2_INVOICES_NEW_DDL)

        # 2. Copy with status mapping. All v1 columns are carried verbatim;
        #    new columns take their migration defaults. legacy_status keeps
        #    the original value.
        conn.execute(
            """
            INSERT INTO invoices_new (
                id, file_hash, original_filename, stored_filename,
                vendor, vendor_tax_id, invoice_number, invoice_date,
                due_date, bill_to, currency,
                subtotal, discount, tax, tax_rate, total,
                status, extraction_json, error_message, page_count,
                created_at, updated_at,
                file_type, legacy_status, extract_attempts
            )
            SELECT
                id, file_hash, original_filename, stored_filename,
                vendor, vendor_tax_id, invoice_number, invoice_date,
                due_date, bill_to, currency,
                subtotal, discount, tax, tax_rate, total,
                CASE status
                    WHEN 'extracted' THEN 'completed'
                    WHEN 'saved' THEN 'completed'
                    ELSE status
                END,
                extraction_json, error_message, page_count,
                created_at, updated_at,
                'pdf', status, 0
            FROM invoices
            """
        )

        # 3. Swap the tables. invoice_lines keeps referencing "invoices";
        #    the name is restored by the rename.
        conn.execute("DROP TABLE invoices")
        conn.execute("ALTER TABLE invoices_new RENAME TO invoices")

        # 4. Lines table gains the per-line tax column (v1 rows keep NULL).
        if "line_tax" not in _columns(conn, "invoice_lines"):
            conn.execute("ALTER TABLE invoice_lines ADD COLUMN line_tax REAL")

        # 5. Audit table + v2 indexes (v1's hash/number indexes are
        #    recreated so the migrated shape matches a fresh v2 database).
        conn.execute(_AUDIT_DDL)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_invoices_hash ON invoices(file_hash)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_invoices_number "
            "ON invoices(invoice_number)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_invoices_vendor_number "
            "ON invoices(vendor, invoice_number)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_invoice "
            "ON invoice_audit(invoice_id, id)"
        )

        # 6. Exactly one record_migrated audit row per pre-existing invoice.
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        migrated = conn.execute(
            "SELECT id, legacy_status FROM invoices ORDER BY id"
        ).fetchall()
        for invoice_id, legacy_status in migrated:
            conn.execute(
                "INSERT INTO invoice_audit "
                "(invoice_id, event_type, actor, details, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    invoice_id,
                    "record_migrated",
                    "system",
                    f"migrated from schema v1 (legacy status '{legacy_status}')",
                    now,
                ),
            )

        conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.OperationalError:
            pass  # transaction was never opened
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")

    # 7. Hard gate: the rebuild must leave zero foreign-key violations.
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise RuntimeError(
            f"migration produced foreign-key violations: {violations!r}"
        )

    conn.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")
