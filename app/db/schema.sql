-- Invoice Processing System — SQLite schema v2 (Sprint E0, enhancement
-- assignment; supersedes the v1 Invoice Extractor schema).
--
-- Money representation (approved decision M-3 / T-E, unchanged): monetary
-- columns are SQLite REAL. All money parsing, validation, arithmetic, and
-- comparison is done in Python with decimal.Decimal at the application
-- boundaries; values are quantized to 2 decimal places before storage and
-- re-quantized on read. Do NOT do money math in SQL.
--
-- Status control: the CHECK below is transitional — it lists the eight
-- canonical lifecycle states PLUS the two v1 statuses ('extracted',
-- 'saved') that pre-enhancement code paths still write. Authoritative
-- transition control lives in app/services/workflow.py, which only accepts
-- the eight canonical states. The two deprecated values are removed by a
-- tightening migration planned for Sprint E5, once the review/save flow is
-- rewired onto the new lifecycle.
--
-- Legacy v1 databases are upgraded by app/db/migrations.py (versioned via
-- PRAGMA user_version; see init_db in app/db/__init__.py). This file is the
-- canonical DDL for fresh databases and is re-asserted idempotently on boot.

CREATE TABLE IF NOT EXISTS invoices (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    file_hash         TEXT NOT NULL,           -- SHA-256; indexed, NOT unique:
                                               -- duplicates warn but may override
    original_filename TEXT NOT NULL,
    stored_filename   TEXT NOT NULL,           -- server-generated UUID name
    file_type         TEXT NOT NULL DEFAULT 'pdf',  -- 'pdf' | 'image' (E2)
    vendor            TEXT,
    vendor_tax_id     TEXT,                    -- GSTIN/VAT/...
    invoice_number    TEXT,
    invoice_date      TEXT,                    -- ISO 8601 (YYYY-MM-DD)
    due_date          TEXT,                    -- ISO 8601 (YYYY-MM-DD)
    bill_to           TEXT,                    -- customer name
    bill_to_address   TEXT,                    -- enhancement §6 (E3)
    ship_to_name      TEXT,                    -- enhancement §6 (E3)
    ship_to_address   TEXT,                    -- enhancement §6 (E3)
    currency          TEXT,
    po_number         TEXT,                    -- enhancement §6 (E3)
    subtotal          REAL,
    discount          REAL,
    tax               REAL,
    tax_rate          REAL,
    total             REAL,
    status            TEXT NOT NULL
                      CHECK (status IN (
                          'uploaded', 'processing', 'completed',
                          'validation_failed', 'pending_approval',
                          'approved', 'rejected', 'failed')),
    legacy_status     TEXT,                    -- pre-migration status (set by migrations)
    extraction_json   TEXT,                    -- per-field status/source draft
    raw_response      TEXT,                    -- AI raw response, size-capped (E2)
    validation_status TEXT,                    -- passed | warning | failed (E3)
    validation_json   TEXT,                    -- finding list (E3)
    dup_status        TEXT,                    -- none | possible | exact (E3)
    dup_matches       TEXT,                    -- JSON match list + reasons (E3)
    approver_role     TEXT,                    -- manager | finance (E4)
    rejection_reason  TEXT,                    -- mandatory on reject (E4)
    acted_by          TEXT,                    -- actor of last approval action (E4)
    acted_at          TEXT,                    -- timestamp of last approval action (E4)
    extract_attempts  INTEGER NOT NULL DEFAULT 0,
    error_message     TEXT,
    page_count        INTEGER,
    created_at        TEXT,
    updated_at        TEXT
);

CREATE TABLE IF NOT EXISTS invoice_lines (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id  INTEGER NOT NULL
                REFERENCES invoices(id) ON DELETE CASCADE,
    line_number INTEGER,
    description TEXT,
    quantity    REAL,
    unit_price  REAL,
    amount      REAL,
    line_tax    REAL                           -- per-line tax (enhancement §6, E3)
);

CREATE TABLE IF NOT EXISTS invoice_audit (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id  INTEGER NOT NULL
                REFERENCES invoices(id) ON DELETE CASCADE,
    event_type  TEXT NOT NULL,                 -- see app/services/audit.py
    actor       TEXT NOT NULL DEFAULT 'system',
    details     TEXT,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_invoices_hash   ON invoices(file_hash);
CREATE INDEX IF NOT EXISTS idx_invoices_number ON invoices(invoice_number);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
CREATE INDEX IF NOT EXISTS idx_invoices_vendor_number
    ON invoices(vendor, invoice_number);
CREATE INDEX IF NOT EXISTS idx_audit_invoice
    ON invoice_audit(invoice_id, id);
