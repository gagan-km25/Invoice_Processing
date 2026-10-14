"""Sprint E5 migration tests — v2 → v3 tightening (US-E5-3).

Rehearsal pattern per the approved E0 safety rule: a genuine v2 database
is built from the v2 rebuild DDL (the exact shape migrate_v1_to_v2
produces), COPIED, and only the copy is migrated via create_app →
init_db. The reference copy is never migrated — the byte-level proof of
source preservation is part of the tests.

Test IDs:
- TC-MIG-V3-00/00b  copied-database rehearsal; source bytes preserved
- TC-MIG-V3-01      status mapping + legacy_status + record_migrated rows
- TC-MIG-V3-02      tightened CHECK refuses extracted/saved
- TC-MIG-V3-03      columns/lines/fk-gate/cascade preserved
- TC-MIG-V3-04      migrated shape == fresh v3 shape (columns + DDL)
- TC-MIG-V3-05      a v1 database chains v1→v2→v3 on one boot
- TC-MIG-V3-06      idempotent boots
"""
import hashlib
import shutil
import sqlite3

import pytest

from app import create_app
from app.db.migrations import _AUDIT_DDL, _V2_INVOICES_NEW_DDL

T1 = "2026-10-06T08:00:00+00:00"
T2 = "2026-10-06T09:30:00+00:00"

V2_INVOICES = [
    {"id": 1, "file_hash": "h-1", "original_filename": "native.pdf",
     "stored_filename": "s-1.pdf", "file_type": "pdf", "vendor": "Acme",
     "vendor_tax_id": None, "invoice_number": "N-1",
     "invoice_date": "2026-09-30", "due_date": None, "bill_to": None,
     "bill_to_address": None, "ship_to_name": None, "ship_to_address": None,
     "currency": "USD", "po_number": None, "subtotal": 100.0,
     "discount": None, "tax": 8.0, "tax_rate": 8.0, "total": 108.0,
     "status": "completed", "legacy_status": None, "extraction_json": "{}",
     "raw_response": None, "validation_status": "passed",
     "validation_json": "[]", "dup_status": "none", "dup_matches": "[]",
     "approver_role": None, "rejection_reason": None, "acted_by": None,
     "acted_at": None, "extract_attempts": 1, "error_message": None,
     "page_count": 1, "created_at": T1, "updated_at": T2},
    {"id": 2, "file_hash": "h-2", "original_filename": "legacy-x.pdf",
     "stored_filename": "s-2.pdf", "file_type": "pdf", "vendor": "Beta",
     "vendor_tax_id": None, "invoice_number": "N-2", "invoice_date": None,
     "due_date": None, "bill_to": None, "bill_to_address": None,
     "ship_to_name": None, "ship_to_address": None, "currency": None,
     "po_number": None, "subtotal": None, "discount": None, "tax": None,
     "tax_rate": None, "total": None, "status": "extracted",
     "legacy_status": None, "extraction_json": None, "raw_response": None,
     "validation_status": None, "validation_json": None, "dup_status": None,
     "dup_matches": None, "approver_role": None, "rejection_reason": None,
     "acted_by": None, "acted_at": None, "extract_attempts": 0,
     "error_message": None, "page_count": None, "created_at": T1,
     "updated_at": T1},
    {"id": 3, "file_hash": "h-3", "original_filename": "legacy-s.pdf",
     "stored_filename": "s-3.pdf", "file_type": "pdf", "vendor": "Gamma",
     "vendor_tax_id": None, "invoice_number": "N-3",
     "invoice_date": "2026-08-01", "due_date": None, "bill_to": None,
     "bill_to_address": None, "ship_to_name": None, "ship_to_address": None,
     "currency": "INR", "po_number": "PO-9", "subtotal": 500.0,
     "discount": None, "tax": 90.0, "tax_rate": 18.0, "total": 590.0,
     "status": "saved",
     # a v1→v2-migrated row: legacy_status already carries the v1 value
     "legacy_status": "saved", "extraction_json": None,
     "raw_response": None, "validation_status": None,
     "validation_json": None, "dup_status": None, "dup_matches": None,
     "approver_role": None, "rejection_reason": None, "acted_by": None,
     "acted_at": None, "extract_attempts": 0, "error_message": None,
     "page_count": 1, "created_at": T1, "updated_at": T1},
    {"id": 4, "file_hash": "h-4", "original_filename": "pending.pdf",
     "stored_filename": "s-4.pdf", "file_type": "pdf", "vendor": "Delta",
     "vendor_tax_id": None, "invoice_number": "N-4",
     "invoice_date": "2026-09-01", "due_date": None, "bill_to": None,
     "bill_to_address": None, "ship_to_name": None, "ship_to_address": None,
     "currency": "USD", "po_number": None, "subtotal": 10.0,
     "discount": None, "tax": 0.8, "tax_rate": 8.0, "total": 10.8,
     "status": "pending_approval", "legacy_status": None,
     "extraction_json": None, "raw_response": None,
     "validation_status": "passed", "validation_json": "[]",
     "dup_status": "none", "dup_matches": "[]", "approver_role": "manager",
     "rejection_reason": None, "acted_by": None, "acted_at": None,
     "extract_attempts": 1, "error_message": None, "page_count": 1,
     "created_at": T1, "updated_at": T2},
]

V2_LINES = [
    {"invoice_id": 1, "line_number": 1, "description": "Widget",
     "quantity": 2.0, "unit_price": 50.0, "amount": 100.0, "line_tax": 2.5},
]


def _open(path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _snapshot(path) -> dict:
    """Full value snapshot of invoices + lines + version, for comparisons."""
    conn = _open(path)
    try:
        invoices = {
            row["id"]: dict(row)
            for row in conn.execute("SELECT * FROM invoices ORDER BY id")
        }
        lines = [dict(row) for row in conn.execute(
            "SELECT * FROM invoice_lines ORDER BY id")]
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        return {"invoices": invoices, "lines": lines, "version": version}
    finally:
        conn.close()


def _make_v2_db(path) -> None:
    """Build a genuine v2 database from the v2 rebuild DDL, stamp it v2,
    and seed rows across canonical + transitional statuses."""
    conn = sqlite3.connect(path)
    try:
        conn.execute(_V2_INVOICES_NEW_DDL)  # builds `invoices_new`…
        conn.execute("ALTER TABLE invoices_new RENAME TO invoices")  # …v2 name
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS invoice_lines (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id  INTEGER NOT NULL
                            REFERENCES invoices(id) ON DELETE CASCADE,
                line_number INTEGER,
                description TEXT,
                quantity    REAL,
                unit_price  REAL,
                amount      REAL,
                line_tax    REAL
            )
            """
        )
        conn.execute(_AUDIT_DDL)
        for row in V2_INVOICES:
            cols = ", ".join(row)
            marks = ", ".join("?" for _ in row)
            conn.execute(
                f"INSERT INTO invoices ({cols}) VALUES ({marks})",
                tuple(row.values()),
            )
        for line in V2_LINES:
            cols = ", ".join(line)
            marks = ", ".join("?" for _ in line)
            conn.execute(
                f"INSERT INTO invoice_lines ({cols}) VALUES ({marks})",
                tuple(line.values()),
            )
        conn.execute(
            "INSERT INTO invoice_audit (invoice_id, event_type, actor, "
            "details, created_at) VALUES (1, 'invoice_uploaded', 'vendor', "
            "NULL, ?)",
            (T1,),
        )
        conn.execute("PRAGMA user_version = 2")
        conn.commit()
    finally:
        conn.close()


@pytest.fixture()
def v2_pair(tmp_path):
    """A v2 database plus a copy; the reference is never migrated — the
    byte-level proof that the rehearsal leaves its source untouched."""
    reference = tmp_path / "v2-reference.db"
    copy = tmp_path / "v2-copy.db"
    _make_v2_db(reference)
    shutil.copy(reference, copy)
    return reference, copy


@pytest.fixture()
def v3_migrated(v2_pair, make_app_config):
    reference, copy = v2_pair
    create_app(make_app_config(database=copy))  # init_db: v2 → v3
    return reference, copy


def test_v3_rehearsal_source_version_untouched(v3_migrated):
    """TC-MIG-V3-00 — the copied-database rehearsal: the migrated copy is
    v3 while the source is still stamped v2."""
    reference, copy = v3_migrated
    assert _open(copy).execute("PRAGMA user_version").fetchone()[0] == 3
    assert _open(reference).execute("PRAGMA user_version").fetchone()[0] == 2


def test_v3_rehearsal_source_bytes_identical(v2_pair, make_app_config):
    """TC-MIG-V3-00b — byte-for-byte: hashing the source before and after
    the copy's migration proves the source was preserved."""
    reference, copy = v2_pair
    before = hashlib.sha256(reference.read_bytes()).hexdigest()
    create_app(make_app_config(database=copy))
    after = hashlib.sha256(reference.read_bytes()).hexdigest()
    assert before == after
    assert _open(copy).execute("PRAGMA user_version").fetchone()[0] == 3


def test_v3_status_mapping_and_legacy_records(v3_migrated):
    """TC-MIG-V3-01 — extracted/saved → completed; legacy_status records
    the prior value (preserving an existing v1→v2 lineage); exactly one
    record_migrated audit row per remapped invoice; canonical rows are
    untouched with no migration audit row; the seeded audit row survives."""
    _, copy = v3_migrated
    conn = _open(copy)
    try:
        rows = {row["id"]: dict(row) for row in
                conn.execute("SELECT * FROM invoices ORDER BY id")}
        migrated_events = [
            (row["invoice_id"], row["details"])
            for row in conn.execute(
                "SELECT invoice_id, details FROM invoice_audit "
                "WHERE event_type = 'record_migrated' ORDER BY id")
        ]
        audits = conn.execute(
            "SELECT COUNT(*) FROM invoice_audit").fetchone()[0]
    finally:
        conn.close()
    assert rows[1]["status"] == "completed"       # native v2 canonical
    assert rows[1]["legacy_status"] is None
    assert rows[2]["status"] == "completed"
    assert rows[2]["legacy_status"] == "extracted"
    assert rows[3]["status"] == "completed"
    assert rows[3]["legacy_status"] == "saved"    # v1 lineage preserved
    assert rows[4]["status"] == "pending_approval"
    assert rows[4]["approver_role"] == "manager"  # E4 columns verbatim
    assert {invoice_id for invoice_id, _ in migrated_events} == {2, 3}
    assert all("schema v2" in details for _, details in migrated_events)
    assert audits == 3  # 1 seeded + 2 record_migrated


def test_v3_check_rejects_transitional_statuses(v3_migrated):
    """TC-MIG-V3-02 — the tightened CHECK refuses extracted/saved."""
    conn = _open(v3_migrated[1])
    try:
        for status in ("extracted", "saved"):
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO invoices (file_hash, original_filename, "
                    "stored_filename, status) VALUES ('x', 'x', 'x', ?)",
                    (status,),
                )
    finally:
        conn.close()


def test_v3_preserves_columns_lines_and_fk_gate(v3_migrated):
    """TC-MIG-V3-03 — every non-remapped column is verbatim; lines (with
    line_tax) survive; foreign_key_check is clean; the cascade still
    removes a deleted invoice's lines."""
    reference, copy = v3_migrated
    source = _snapshot(reference)["invoices"]
    target = _snapshot(copy)["invoices"]
    for invoice_id, before in source.items():
        after = target[invoice_id]
        for column, value in before.items():
            if column == "status":
                continue  # remapping asserted separately
            if (column == "legacy_status" and value is None
                    and before["status"] in ("extracted", "saved")):
                continue  # COALESCE filled it from the remapped status
            assert after[column] == value, (invoice_id, column)

    conn = _open(copy)
    try:
        lines = [dict(row) for row in conn.execute(
            "SELECT * FROM invoice_lines ORDER BY id")]
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM invoices WHERE id = 1")
        conn.commit()
        remaining = conn.execute(
            "SELECT COUNT(*) FROM invoice_lines WHERE invoice_id = 1"
        ).fetchone()[0]
    finally:
        conn.close()
    assert lines[0]["line_tax"] == 2.5
    assert remaining == 0


def test_v3_shape_matches_fresh_database(v2_pair, make_app_config, tmp_path):
    """TC-MIG-V3-04 — a migrated v2 database and a fresh v3 database share
    the same columns AND a semantically identical tightened CHECK: all
    eight canonical statuses present, no transitional aliases in either
    (the DDL *text* differs — schema.sql carries comments — so the
    comparison is semantic)."""
    reference, copy = v2_pair
    fresh = tmp_path / "fresh-v3.db"
    create_app(make_app_config(database=fresh))
    create_app(make_app_config(database=copy))

    CANONICAL = ("uploaded", "processing", "completed", "validation_failed",
                 "pending_approval", "approved", "rejected", "failed")

    def shape(path):
        conn = _open(path)
        try:
            columns = [row["name"] for row in conn.execute(
                "PRAGMA table_info(invoices)")]
            ddl = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' "
                "AND name = 'invoices'").fetchone()[0]
            return columns, ddl
        finally:
            conn.close()

    fresh_columns, fresh_ddl = shape(fresh)
    migrated_columns, migrated_ddl = shape(copy)
    assert fresh_columns == migrated_columns
    for ddl in (fresh_ddl, migrated_ddl):
        for status in CANONICAL:
            assert f"'{status}'" in ddl, status
        assert "'extracted'" not in ddl and "'saved'" not in ddl


@pytest.fixture()
def v1_pair(tmp_path):
    """A genuine v1 database plus a copy (shared builder with
    test_migration.py, whose fixture is not importable as a fixture)."""
    from test_migration import _make_v1_db

    reference = tmp_path / "v1-reference.db"
    copy = tmp_path / "v1-copy.db"
    _make_v1_db(reference)
    shutil.copy(reference, copy)
    return reference, copy


def test_v1_database_chains_to_v3(v1_pair, make_app_config):
    """TC-MIG-V3-05 — a v1 database upgrades through both steps on one
    boot and lands at v3 with the tightened CHECK; the reference v1 stays
    unmigrated (version 0)."""
    reference, copy = v1_pair
    create_app(make_app_config(database=copy))
    conn = _open(copy)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
        ddl = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' "
            "AND name = 'invoices'").fetchone()[0]
        assert "'extracted'" not in ddl and "'saved'" not in ddl
    finally:
        conn.close()
    assert _open(reference).execute("PRAGMA user_version").fetchone()[0] == 0


def test_v3_migration_is_idempotent(v3_migrated, make_app_config):
    """TC-MIG-V3-06 — second and third boots are no-ops: data, audits,
    and version unchanged."""
    _, copy = v3_migrated
    before = _snapshot(copy)
    create_app(make_app_config(database=copy))
    create_app(make_app_config(database=copy))
    after = _snapshot(copy)
    assert before == after
    assert after["version"] == 3
