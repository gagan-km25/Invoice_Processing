"""Sprint E3 unit tests — duplicate classification (assignment §9).

DB-backed unit tests against a temporary database (conftest `app`): the
classifier is exercised through its real repository seam. Rows are seeded
directly (INSERT via repository, field UPDATE via test SQL — the same
pattern the E1 pipeline tests use for fixtures).
"""
import sqlite3
import uuid

import pytest

from app.db import get_db
from app.db.repository import insert_invoice
from app.services.duplicates import (
    CLASSIFICATION_EXACT,
    CLASSIFICATION_NONE,
    CLASSIFICATION_POSSIBLE,
    classify,
)


def _conn(app):
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    return conn


def _seed(app, *, vendor="Acme Corporation", invoice_number="INV-1",
          invoice_date="2026-09-30", total="108.00",
          status="completed", file_hash=None):
    """Insert one invoice with structured fields; returns its id."""
    unique = uuid.uuid4().hex[:8]
    with app.app_context():
        invoice_id = insert_invoice(
            get_db(),
            file_hash=file_hash or f"hash-{unique}",
            original_filename=f"{invoice_number}-{unique}.pdf",
            stored_filename=f"uuid-{invoice_number}-{unique}.pdf",
            status=status,
            page_count=1,
        )
    conn = _conn(app)
    try:
        conn.execute(
            "UPDATE invoices SET vendor = ?, invoice_number = ?, "
            "invoice_date = ?, total = ? WHERE id = ?",
            (vendor, invoice_number, invoice_date, total, invoice_id),
        )
        conn.commit()
    finally:
        conn.close()
    return invoice_id


def _classify(app, invoice_id):
    with app.app_context():
        conn = get_db()
        try:
            return classify(conn, invoice_id)
        finally:
            conn.close()


def test_missing_record_classifies_none(app):
    """An unknown id cannot be classified — none, no crash."""
    assert _classify(app, 9999)["classification"] == CLASSIFICATION_NONE


def test_no_candidates_classifies_none(app):
    """A lone invoice has nobody to match — none."""
    solo = _seed(app, invoice_number="INV-SOLO")
    assert _classify(app, solo)["classification"] == CLASSIFICATION_NONE


def test_exact_duplicate_same_vendor_and_number(app):
    """Exact duplicate: same vendor + number regardless of total/date."""
    first = _seed(app, invoice_number="INV-DUP")
    second = _seed(app, invoice_number="INV-DUP",
                   invoice_date="2026-08-01", total="999.99")
    result = _classify(app, second)
    assert result["classification"] == CLASSIFICATION_EXACT
    assert [match["id"] for match in result["matches"]] == [first]


def test_exact_duplicate_is_case_insensitive(app):
    """Case-insensitive supplier name + number (approved decision 2)."""
    _seed(app, invoice_number="INV-dup")
    other = _seed(app, vendor="  ACME corporation ", invoice_number="inv-DUP")
    result = _classify(app, other)
    assert result["classification"] == CLASSIFICATION_EXACT


def test_possible_duplicate_same_vendor_total_date(app):
    """Possible duplicate: same vendor + exact total + exact invoice date,
    different invoice number (approved decision 2)."""
    first = _seed(app, invoice_number="INV-A")
    second = _seed(app, invoice_number="INV-B")
    result = _classify(app, second)
    assert result["classification"] == CLASSIFICATION_POSSIBLE
    match = result["matches"][0]
    assert match["id"] == first
    assert match["kind"] == "possible"


def test_same_total_different_date_is_none(app):
    _seed(app, invoice_number="INV-A", invoice_date="2026-09-30")
    other = _seed(app, invoice_number="INV-B", invoice_date="2026-09-29")
    assert _classify(app, other)["classification"] == CLASSIFICATION_NONE


def test_same_date_different_total_is_none(app):
    _seed(app, invoice_number="INV-A", total="108.00")
    other = _seed(app, invoice_number="INV-B", total="208.00")
    assert _classify(app, other)["classification"] == CLASSIFICATION_NONE


def test_different_vendor_is_none(app):
    _seed(app, invoice_number="INV-A")
    other = _seed(app, invoice_number="INV-B", vendor="Beta LLC")
    assert _classify(app, other)["classification"] == CLASSIFICATION_NONE


def test_self_is_excluded_from_candidates(app):
    """Re-classifying the same row never matches itself."""
    solo = _seed(app, invoice_number="INV-SELF")
    result = _classify(app, solo)
    assert result["classification"] == CLASSIFICATION_NONE
    assert result["matches"] == []


def test_exact_outranks_possible(app):
    """A candidate matching both rules is reported once, as exact."""
    kept = _seed(app, invoice_number="INV-A", invoice_date="2026-09-30",
                 total="108.00")
    other = _seed(app, invoice_number="INV-A", invoice_date="2026-09-30",
                  total="108.00")
    result = _classify(app, other)
    assert result["classification"] == CLASSIFICATION_EXACT
    assert [match["id"] for match in result["matches"]] == [kept]
    assert result["matches"][0]["kind"] == "exact"


def test_blank_vendor_or_number_classifies_none(app):
    """Without a vendor or number the invoice is not comparable."""
    seed = _seed(app)
    conn = _conn(app)
    try:
        conn.execute("UPDATE invoices SET vendor = NULL WHERE id = ?", (seed,))
        conn.commit()
    finally:
        conn.close()
    assert _classify(app, seed)["classification"] == CLASSIFICATION_NONE


@pytest.mark.parametrize("status", [
    "completed", "validation_failed", "pending_approval",
    "approved", "rejected",
])
def test_candidate_statuses_are_compared(app, status):
    """Approved decision C: every structured state is a candidate (the
    v2-only `saved` alias left the list with the v3 tightening)."""
    _seed(app, invoice_number="INV-CAND", status=status)
    other = _seed(app, invoice_number="INV-CAND", status="completed")
    assert _classify(app, other)["classification"] == CLASSIFICATION_EXACT


@pytest.mark.parametrize("status", ["uploaded", "processing"])
def test_unstructured_statuses_are_not_candidates(app, status):
    """`uploaded`/`processing` rows carry no comparable fields yet — and a
    row mid-processing must not be classified against anyway."""
    _seed(app, invoice_number="INV-BUSY", status=status)
    other = _seed(app, invoice_number="INV-BUSY", status="completed")
    assert _classify(app, other)["classification"] == CLASSIFICATION_NONE


def test_matches_carry_full_explanation(app):
    """Each match explains itself: id, vendor, number, date, total, kind —
    the stored explanation the user sees (§9)."""
    _seed(app, invoice_number="INV-EXPL", vendor="Acme Corporation",
          invoice_date="2026-09-30", total="108.00")
    other = _seed(app, invoice_number="INV-EXPL", vendor="Acme Corporation",
                  invoice_date="2026-09-30", total="108.00")
    match = _classify(app, other)["matches"][0]
    assert set(match) == {"id", "vendor", "invoice_number",
                          "invoice_date", "total", "kind"}
    assert match["vendor"] == "Acme Corporation"
    assert match["invoice_number"] == "INV-EXPL"
    assert match["invoice_date"] == "2026-09-30"
    assert match["total"] == 108.00
    assert match["kind"] == "exact"
