"""Sprint E0 migration tests — v1 → v2 on a COPY, never on a live database.

Test IDs (approved plan §5, strengthened per review):
- TC-MIG-01  invoice IDs preserved (set, max, AUTOINCREMENT continues)
- TC-MIG-02  all field values preserved per column (NULLs, unicode, REALs)
- TC-MIG-03  timestamps byte-identical
- TC-MIG-04  line items preserved (values, mapping, order); line_tax NULL
- TC-MIG-05  FK integrity: foreign_key_check empty; cascade still works
- TC-MIG-06  idempotent: second boot is a no-op (data, audit count, version)
- TC-MIG-07  status mapping + legacy_status + one record_migrated audit row
- TC-MIG-09  migrated schema == fresh schema (column-for-column)

The fixture builds a genuine v1 database (exact committed v1 DDL), copies
it with shutil.copy, and migrates only the copy via create_app → init_db.
"""
import shutil
import sqlite3

import pytest

from app import create_app
from app.db.migrations import CURRENT_SCHEMA_VERSION

# The committed v1 schema (Sprint 0..6), reproduced verbatim so the fixture
# is a genuine legacy database. If the v1 DDL on master ever changes, this
# literal is the reference for what "legacy" means.
V1_SCHEMA = """
CREATE TABLE IF NOT EXISTS invoices (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    file_hash         TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    stored_filename   TEXT NOT NULL,
    vendor            TEXT,
    vendor_tax_id     TEXT,
    invoice_number    TEXT,
    invoice_date      TEXT,
    due_date          TEXT,
    bill_to           TEXT,
    currency          TEXT,
    subtotal          REAL,
    discount          REAL,
    tax               REAL,
    tax_rate          REAL,
    total             REAL,
    status            TEXT NOT NULL
                      CHECK (status IN ('uploaded', 'extracted', 'saved', 'failed')),
    extraction_json   TEXT,
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
"""

V1_COLUMNS = [
    "id", "file_hash", "original_filename", "stored_filename", "vendor",
    "vendor_tax_id", "invoice_number", "invoice_date", "due_date", "bill_to",
    "currency", "subtotal", "discount", "tax", "tax_rate", "total", "status",
    "extraction_json", "error_message", "page_count", "created_at",
    "updated_at",
]

T1 = "2026-10-06T08:00:00+00:00"
T2 = "2026-10-06T09:30:00+00:00"

# Five invoices covering all four legacy statuses, NULLs, unicode, and
# REAL amounts — one row per dict of v1 column -> value.
V1_INVOICES = [
    {
        "id": 1, "file_hash": "hash-001", "original_filename": "acme.pdf",
        "stored_filename": "uuid-001.pdf", "vendor": "Acme GmbH",
        "vendor_tax_id": "DE123456789", "invoice_number": "INV-001",
        "invoice_date": "2026-09-30", "due_date": "2026-10-30",
        "bill_to": "Buyer One", "currency": "EUR", "subtotal": 100.0,
        "discount": 0.0, "tax": 19.0, "tax_rate": 19.0, "total": 119.0,
        "status": "saved", "extraction_json": '{"fields": {}}',
        "error_message": None, "page_count": 2, "created_at": T1,
        "updated_at": T2,
    },
    {
        "id": 2, "file_hash": "hash-002", "original_filename": "partial.pdf",
        "stored_filename": "uuid-002.pdf", "vendor": None,
        "vendor_tax_id": None, "invoice_number": None, "invoice_date": None,
        "due_date": None, "bill_to": None, "currency": None,
        "subtotal": None, "discount": None, "tax": None, "tax_rate": None,
        "total": None, "status": "extracted", "extraction_json": None,
        "error_message": None, "page_count": 1, "created_at": T1,
        "updated_at": T1,
    },
    {
        "id": 3, "file_hash": "hash-003", "original_filename": "fresh.pdf",
        "stored_filename": "uuid-003.pdf", "vendor": None,
        "vendor_tax_id": None, "invoice_number": None, "invoice_date": None,
        "due_date": None, "bill_to": None, "currency": None,
        "subtotal": None, "discount": None, "tax": None, "tax_rate": None,
        "total": None, "status": "uploaded", "extraction_json": None,
        "error_message": None, "page_count": 1, "created_at": T1,
        "updated_at": T1,
    },
    {
        "id": 4, "file_hash": "hash-004", "original_filename": "scan.pdf",
        "stored_filename": "uuid-004.pdf", "vendor": None,
        "vendor_tax_id": None, "invoice_number": None, "invoice_date": None,
        "due_date": None, "bill_to": None, "currency": None,
        "subtotal": None, "discount": None, "tax": None, "tax_rate": None,
        "total": None, "status": "failed",
        "extraction_json": None,
        "error_message": "The PDF contains no selectable text.",
        "page_count": 3, "created_at": T1, "updated_at": T1,
    },
    {
        "id": 5, "file_hash": "hash-005",
        "original_filename": "müller.pdf", "stored_filename": "uuid-005.pdf",
        "vendor": "Müller & Co. 中文", "vendor_tax_id": "IN27AAPFU093961",
        "invoice_number": "MC/2026/Ω-7", "invoice_date": "2026-10-01",
        "due_date": None, "bill_to": None, "currency": "INR",
        "subtotal": 4250.55, "discount": -5.5, "tax": 765.1,
        "tax_rate": 18.0, "total": 5010.65, "status": "saved",
        "extraction_json": None, "error_message": None, "page_count": 1,
        "created_at": T1, "updated_at": T2,
    },
]

V1_LINES = [
    {"invoice_id": 1, "line_number": 1, "description": "Widget",
     "quantity": 2.0, "unit_price": 40.0, "amount": 80.0},
    {"invoice_id": 1, "line_number": 2, "description": "Gadget",
     "quantity": 1.0, "unit_price": 20.0, "amount": 20.0},
    {"invoice_id": 5, "line_number": 1, "description": "परामर्श सेवा",
     "quantity": 10.5, "unit_price": 300.0, "amount": 3150.0},
]

EXPECTED_V2_STATUS = {
    "saved": "completed",
    "extracted": "completed",
    "uploaded": "uploaded",
    "failed": "failed",
}


def _make_v1_db(path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(V1_SCHEMA)
        for row in V1_INVOICES:
            cols = ", ".join(V1_COLUMNS)
            marks = ", ".join("?" for _ in V1_COLUMNS)
            conn.execute(
                f"INSERT INTO invoices ({cols}) VALUES ({marks})",
                [row[col] for col in V1_COLUMNS],
            )
        for line in V1_LINES:
            conn.execute(
                "INSERT INTO invoice_lines "
                "(invoice_id, line_number, description, quantity, "
                "unit_price, amount) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    line["invoice_id"], line["line_number"],
                    line["description"], line["quantity"],
                    line["unit_price"], line["amount"],
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _open(path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _snapshot(path) -> dict:
    """Full value snapshot of invoices + lines, for before/after comparison."""
    conn = _open(path)
    try:
        invoices = {
            row["id"]: dict(row)
            for row in conn.execute("SELECT * FROM invoices ORDER BY id")
        }
        lines = [
            dict(row)
            for row in conn.execute("SELECT * FROM invoice_lines ORDER BY id")
        ]
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        return {"invoices": invoices, "lines": lines,
                "version": version, "tables": tables}
    finally:
        conn.close()


@pytest.fixture()
def v1_pair(tmp_path):
    """Build a v1 database and a copy; return (reference_path, copy_path).
    The reference never migrates; the copy is what tests migrate."""
    reference = tmp_path / "v1-reference.db"
    copy = tmp_path / "v1-copy.db"
    _make_v1_db(reference)
    shutil.copy(reference, copy)
    return reference, copy


@pytest.fixture()
def migrated(v1_pair, make_app_config):
    """Migrate the copy once via the real boot path and return its path."""
    reference, copy = v1_pair
    create_app(make_app_config(database=copy))
    return copy


# --------------------------------------------------------------------------
# TC-MIG-01 — invoice IDs preserved
# --------------------------------------------------------------------------


def test_migration_preserves_invoice_ids(migrated, v1_pair):
    reference, _ = v1_pair
    ref_ids = set(_snapshot(reference)["invoices"])
    mig_ids = set(_snapshot(migrated)["invoices"])
    assert mig_ids == ref_ids == {1, 2, 3, 4, 5}

    # AUTOINCREMENT continues after the highest migrated id.
    conn = _open(migrated)
    try:
        conn.execute(
            "INSERT INTO invoices (file_hash, original_filename, "
            "stored_filename, status, created_at, updated_at) "
            "VALUES ('h', 'n', 's', 'uploaded', 't', 't')"
        )
        new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        assert new_id == 6
    finally:
        conn.close()


# --------------------------------------------------------------------------
# TC-MIG-02 — every field value preserved per column
# --------------------------------------------------------------------------


def test_migration_preserves_all_field_values(migrated, v1_pair):
    reference, _ = v1_pair
    ref = _snapshot(reference)["invoices"]
    mig = _snapshot(migrated)["invoices"]
    for invoice_id, ref_row in ref.items():
        mig_row = mig[invoice_id]
        for col in V1_COLUMNS:
            if col == "status":
                # The one column that intentionally changes (decision 5);
                # the original value must survive verbatim in legacy_status,
                # and the mapping itself is asserted in TC-MIG-07.
                assert mig_row["legacy_status"] == ref_row["status"]
                continue
            assert mig_row[col] == ref_row[col], (
                f"invoice {invoice_id}: column {col!r} changed during "
                f"migration ({ref_row[col]!r} -> {mig_row[col]!r})"
            )


# --------------------------------------------------------------------------
# TC-MIG-03 — timestamps byte-identical
# --------------------------------------------------------------------------


def test_migration_preserves_timestamps(migrated, v1_pair):
    reference, _ = v1_pair
    ref = _snapshot(reference)["invoices"]
    mig = _snapshot(migrated)["invoices"]
    for invoice_id in ref:
        assert mig[invoice_id]["created_at"] == ref[invoice_id]["created_at"]
        assert mig[invoice_id]["updated_at"] == ref[invoice_id]["updated_at"]
    assert mig[1]["created_at"] == T1
    assert mig[1]["updated_at"] == T2


# --------------------------------------------------------------------------
# TC-MIG-04 — line items preserved; line_tax NULL for legacy rows
# --------------------------------------------------------------------------


def test_migration_preserves_line_items(migrated, v1_pair):
    reference, _ = v1_pair
    ref = _snapshot(reference)["lines"]
    mig = _snapshot(migrated)["lines"]
    assert len(mig) == len(ref) == 3
    for ref_line, mig_line in zip(ref, mig):
        for key in ("invoice_id", "line_number", "description", "quantity",
                    "unit_price", "amount"):
            assert mig_line[key] == ref_line[key], (
                f"line field {key!r} changed: "
                f"{ref_line[key]!r} -> {mig_line[key]!r}"
            )
        assert mig_line["line_tax"] is None  # new column, legacy rows NULL
    assert mig[0]["description"] == "Widget"
    assert mig[2]["description"] == "परामर्श सेवा"


# --------------------------------------------------------------------------
# TC-MIG-05 — foreign-key integrity
# --------------------------------------------------------------------------


def test_migration_fk_integrity(migrated):
    conn = _open(migrated)
    try:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        # cascade delete still works after the rebuild
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM invoices WHERE id = 1")
        conn.commit()
        remaining = conn.execute(
            "SELECT COUNT(*) FROM invoice_lines WHERE invoice_id = 1"
        ).fetchone()[0]
        assert remaining == 0
    finally:
        conn.close()


# --------------------------------------------------------------------------
# TC-MIG-06 — idempotency: second boot is a no-op
# --------------------------------------------------------------------------


def test_migration_is_idempotent(migrated, make_app_config):
    before = _snapshot(migrated)
    audit_before = _audit_count(migrated)

    create_app(make_app_config(database=migrated))  # second boot
    create_app(make_app_config(database=migrated))  # third boot for good measure

    after = _snapshot(migrated)
    assert after == before
    assert _audit_count(migrated) == audit_before == 5  # one per invoice
    assert after["version"] == CURRENT_SCHEMA_VERSION


# --------------------------------------------------------------------------
# TC-MIG-07 — status mapping, legacy_status, record_migrated audit rows
# --------------------------------------------------------------------------


def test_migration_status_mapping_and_audit(migrated):
    snap = _snapshot(migrated)
    invoices = snap["invoices"]

    expected_status = {
        1: "completed",  # saved → completed
        2: "completed",  # extracted → completed
        3: "uploaded",   # unchanged
        4: "failed",     # unchanged
        5: "completed",  # saved → completed
    }
    expected_legacy = {1: "saved", 2: "extracted", 3: "uploaded",
                       4: "failed", 5: "saved"}
    for invoice_id, row in invoices.items():
        assert row["status"] == expected_status[invoice_id]
        assert row["legacy_status"] == expected_legacy[invoice_id]
        assert row["file_type"] == "pdf"
        assert row["extract_attempts"] == 0

    conn = _open(migrated)
    try:
        rows = conn.execute(
            "SELECT invoice_id, event_type, actor, details "
            "FROM invoice_audit ORDER BY invoice_id"
        ).fetchall()
    finally:
        conn.close()
    assert [r["invoice_id"] for r in rows] == [1, 2, 3, 4, 5]
    assert all(r["event_type"] == "record_migrated" for r in rows)
    assert all(r["actor"] == "system" for r in rows)
    assert "legacy status 'saved'" in rows[0]["details"]
    assert "legacy status 'extracted'" in rows[1]["details"]


# --------------------------------------------------------------------------
# TC-MIG-09 — migrated schema == fresh schema (column-for-column)
# --------------------------------------------------------------------------


def test_migrated_schema_matches_fresh_schema(v1_pair, make_app_config, tmp_path):
    _, copy = v1_pair
    fresh = tmp_path / "fresh.db"
    create_app(make_app_config(database=fresh))  # fresh v2 via schema.sql
    create_app(make_app_config(database=copy))   # migrated v1 → v2

    def _shape(path):
        conn = _open(path)
        try:
            tables = {}
            for table in ("invoices", "invoice_lines", "invoice_audit"):
                tables[table] = [
                    (row[1], row[2], row[3], row[5])  # name, type, notnull, pk
                    for row in conn.execute(f"PRAGMA table_info({table})")
                ]
            indexes = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index' "
                    "AND name LIKE 'idx_%'"
                )
            }
            return tables, indexes
        finally:
            conn.close()

    fresh_shape, fresh_indexes = _shape(fresh)
    migrated_shape, migrated_indexes = _shape(copy)
    assert migrated_shape == fresh_shape
    assert migrated_indexes == fresh_indexes


def _audit_count(path) -> int:
    conn = _open(path)
    try:
        return conn.execute("SELECT COUNT(*) FROM invoice_audit").fetchone()[0]
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Safety behaviour — unrecognised databases are refused
# --------------------------------------------------------------------------


def test_init_db_refuses_unknown_shape(make_app_config, tmp_path):
    """A database that claims version >= 2 but lacks v2 columns must never
    be silently 'upgraded'."""
    weird = tmp_path / "weird.db"
    conn = _open(weird)
    try:
        conn.execute("CREATE TABLE invoices (id INTEGER PRIMARY KEY)")
        conn.execute("PRAGMA user_version = 2")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(RuntimeError):
        create_app(make_app_config(database=weird))
