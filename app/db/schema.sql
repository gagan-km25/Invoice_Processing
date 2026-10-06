-- Invoice Extractor — SQLite schema (idempotent, applied on every boot).
--
-- Money representation (approved decision M-3 / T-E): monetary columns are
-- SQLite REAL. All money parsing, validation, arithmetic, and comparison is
-- done in Python with decimal.Decimal at the application boundaries; values
-- are quantized to 2 decimal places before storage and re-quantized on read.
-- Do NOT do money math in SQL.

CREATE TABLE IF NOT EXISTS invoices (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    file_hash         TEXT NOT NULL,           -- SHA-256; indexed, NOT unique:
                                               -- duplicates warn but may override
    original_filename TEXT NOT NULL,
    stored_filename   TEXT NOT NULL,           -- server-generated UUID name
    vendor            TEXT,
    vendor_tax_id     TEXT,                    -- GSTIN/VAT/... (Sprint 2)
    invoice_number    TEXT,
    invoice_date      TEXT,                    -- ISO 8601 (YYYY-MM-DD)
    due_date          TEXT,                    -- ISO 8601 (YYYY-MM-DD)
    bill_to           TEXT,                    -- customer (Sprint 2)
    currency          TEXT,
    subtotal          REAL,
    discount          REAL,                    -- Sprint 2 (exploration finding 5)
    tax               REAL,
    tax_rate          REAL,
    total             REAL,
    status            TEXT NOT NULL
                      CHECK (status IN ('uploaded', 'extracted', 'saved', 'failed')),
    extraction_json   TEXT,                    -- per-field status/source draft
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
    amount      REAL
);

CREATE INDEX IF NOT EXISTS idx_invoices_hash   ON invoices(file_hash);
CREATE INDEX IF NOT EXISTS idx_invoices_number ON invoices(invoice_number);
