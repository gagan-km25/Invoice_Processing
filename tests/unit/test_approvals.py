"""Sprint E4 unit tests — approval submission and decisions
(`app/services/approvals.py`; assignment §10/§11).

DB-backed unit tests against a temporary database (conftest `app`): rows
are seeded directly (repository insert + test UPDATE, the established
fixture pattern). Every refusal test asserts ZERO database writes: the
status, the decision columns, AND the audit row count — an HTTP status
code alone never proves that.
"""
import sqlite3
import uuid
from decimal import Decimal

import pytest

from app.db import get_db
from app.db.repository import get_invoice, insert_invoice
from app.services import approvals
from app.services.roles import ROLE_FINANCE, ROLE_MANAGER, ROLE_VENDOR

THRESHOLD = Decimal("100000.00")


def _conn(app):
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    return conn


def _seed(app, *, status="completed", total="108.00",
          vendor="Acme Corporation", invoice_number="INV-E4-1",
          approver_role=None):
    """Insert one invoice; returns its id."""
    unique = uuid.uuid4().hex[:8]
    with app.app_context():
        invoice_id = insert_invoice(
            get_db(),
            file_hash=f"hash-{unique}",
            original_filename=f"inv-{unique}.pdf",
            stored_filename=f"uuid-{unique}.pdf",
            status=status,
            page_count=1,
        )
    conn = _conn(app)
    try:
        conn.execute(
            "UPDATE invoices SET total = ?, vendor = ?, invoice_number = ?, "
            "approver_role = ? WHERE id = ?",
            (float(total) if total is not None else None,
             vendor, invoice_number, approver_role, invoice_id),
        )
        conn.commit()
    finally:
        conn.close()
    return invoice_id


def _snapshot(app, invoice_id):
    """(status, approver_role, acted_by, acted_at, rejection_reason, audit_count)."""
    conn = _conn(app)
    try:
        row = conn.execute(
            "SELECT status, approver_role, acted_by, acted_at, rejection_reason "
            "FROM invoices WHERE id = ?", (invoice_id,)
        ).fetchone()
        audits = conn.execute(
            "SELECT COUNT(*) FROM invoice_audit WHERE invoice_id = ?",
            (invoice_id,),
        ).fetchone()[0]
    finally:
        conn.close()
    return (*tuple(row), audits)


def _call_submit(app, invoice_id, threshold=THRESHOLD):
    with app.app_context():
        conn = get_db()
        try:
            return approvals.submit(conn, invoice_id, threshold=threshold)
        finally:
            conn.close()


def _call_decide(app, invoice_id, *, action, role, reason=None):
    with app.app_context():
        conn = get_db()
        try:
            return approvals.decide(
                conn, invoice_id, action=action, role=role, reason=reason
            )
        finally:
            conn.close()


# ------------------------------------------------------- §10: submission

def test_submit_routes_manager_below_threshold(app):
    """Total < ₹1,00,000 → manager; one transaction writes the status,
    `approver_role`, and both audit entries."""
    invoice_id = _seed(app, total="99999.99")
    result = _call_submit(app, invoice_id)
    assert result["ok"] is True and result["approver_role"] == "manager"
    status, role, acted_by, acted_at, reason, audits = _snapshot(app, invoice_id)
    assert (status, role) == ("pending_approval", "manager")
    events = _event_names(app, invoice_id)
    assert events == ["review_submitted", "approval_assigned"]
    assert "manager" in _last_details(app, invoice_id)


def test_submit_routes_finance_at_threshold(app):
    """Total == ₹1,00,000 → finance (the assignment boundary is >=)."""
    invoice_id = _seed(app, total="100000.00")
    result = _call_submit(app, invoice_id)
    assert result["ok"] is True and result["approver_role"] == "finance"


def test_submit_routes_finance_above_threshold(app):
    invoice_id = _seed(app, total="100000.01")
    assert _call_submit(app, invoice_id)["approver_role"] == "finance"


def test_submit_from_validation_failed_allowed(app):
    invoice_id = _seed(app, status="validation_failed", total="500.00")
    assert _call_submit(app, invoice_id)["ok"] is True
    assert _snapshot(app, invoice_id)[0] == "pending_approval"


def test_submit_refused_when_total_is_null(app):
    """Approved decision 1: a total-less invoice is refused with a clear
    message — never silently defaulted to Finance. Zero writes."""
    invoice_id = _seed(app, status="validation_failed", total=None)
    result = _call_submit(app, invoice_id)
    assert result["ok"] is False
    assert "total" in result["error"].lower()
    assert "routing" in result["error"].lower()
    assert _snapshot(app, invoice_id) == ("validation_failed", None, None, None, None, 0)


def test_submit_refused_from_terminal_states(app):
    """E4 decision 3 carried through E5: only completed /
    validation_failed are submittable. (`saved` itself was removed by the
    v3 schema tightening — inserting it is now impossible, covered by
    tests/unit/test_migration_v3.py.)"""
    approved = _seed(app, status="approved", approver_role="manager")
    result = _call_submit(app, approved)
    assert result["ok"] is False and "approved" in result["error"]
    assert _snapshot(app, approved)[0] == "approved"
    assert _snapshot(app, approved)[5] == 0

    rejected = _seed(app, status="rejected")
    result = _call_submit(app, rejected)
    assert result["ok"] is False and "rejected" in result["error"]
    assert _snapshot(app, rejected)[0] == "rejected"
    assert _snapshot(app, rejected)[5] == 0


def test_submit_refused_from_pending_approval(app):
    """Double submission: refused, zero additional writes."""
    invoice_id = _seed(app)
    assert _call_submit(app, invoice_id)["ok"] is True
    before = _snapshot(app, invoice_id)
    result = _call_submit(app, invoice_id)
    assert result["ok"] is False and "pending_approval" in result["error"]
    assert _snapshot(app, invoice_id) == before


def test_submit_refused_for_missing_record(app):
    result = _call_submit(app, 9999)
    assert result["ok"] is False and result["error_kind"] == "missing"


# --------------------------------------------- §11: approve / reject

def test_approve_by_matching_role(app):
    invoice_id = _seed(app, approver_role="manager")
    with app.app_context():  # route the record first
        _call_submit(app, invoice_id)
    result = _call_decide(app, invoice_id, action="approve", role=ROLE_MANAGER)
    assert result["ok"] is True
    status, role, acted_by, acted_at, reason, audits = _snapshot(app, invoice_id)
    assert status == "approved"
    assert acted_by == ROLE_MANAGER and acted_at
    assert reason is None  # approvals never store a reason
    assert _event_names(app, invoice_id)[-1] == "invoice_approved"
    assert _actor_of_last(app, invoice_id) == ROLE_MANAGER


def test_approve_ignores_reason_even_if_posted(app):
    """A posted `reason` on approve is never stored (nothing to reject)."""
    invoice_id = _seed(app, approver_role="manager")
    _call_submit(app, invoice_id)
    _call_decide(app, invoice_id, action="approve", role=ROLE_MANAGER,
                 reason="should be ignored")
    assert _snapshot(app, invoice_id)[4] is None


def test_reject_requires_reason(app):
    """Blank/whitespace reasons are refused — zero writes."""
    invoice_id = _seed(app)
    _call_submit(app, invoice_id)  # 108.00 → manager-routed
    for reason in (None, "", "   "):
        result = _call_decide(app, invoice_id, action="reject",
                              role=ROLE_MANAGER, reason=reason)
        assert result["ok"] is False and result["error_kind"] == "invalid"
        assert "reason" in result["error"].lower()
        assert _snapshot(app, invoice_id)[0] == "pending_approval"
        assert _snapshot(app, invoice_id)[5] == 2  # only the submit audits


def test_reject_stores_reason_and_decision_columns(app):
    invoice_id = _seed(app, approver_role="manager")
    _call_submit(app, invoice_id)
    result = _call_decide(app, invoice_id, action="reject",
                          role=ROLE_MANAGER, reason="Amount not billable")
    assert result["ok"] is True
    status, role, acted_by, acted_at, reason, audits = _snapshot(app, invoice_id)
    assert (status, reason) == ("rejected", "Amount not billable")
    assert acted_by == ROLE_MANAGER and acted_at
    assert _event_names(app, invoice_id)[-1] == "invoice_rejected"


def test_mismatched_approver_role_forbidden_zero_writes(app):
    """Finance acting on a manager-routed invoice → forbidden, and the
    database (status, decision columns, audit count) is untouched."""
    invoice_id = _seed(app, approver_role="manager")
    _call_submit(app, invoice_id)
    before = _snapshot(app, invoice_id)
    result = _call_decide(app, invoice_id, action="approve", role=ROLE_FINANCE)
    assert result["ok"] is False and result["error_kind"] == "forbidden"
    assert _snapshot(app, invoice_id) == before


def test_vendor_cannot_decide_zero_writes(app):
    invoice_id = _seed(app, approver_role="manager")
    _call_submit(app, invoice_id)
    before = _snapshot(app, invoice_id)
    for action in ("approve", "reject"):
        result = _call_decide(app, invoice_id, action=action, role=ROLE_VENDOR,
                              reason="why not")
        assert result["ok"] is False and result["error_kind"] == "forbidden"
    assert _snapshot(app, invoice_id) == before


def test_decide_refused_from_terminal_states(app):
    """Approved→Approved / Approved→Rejected / Rejected→anything: the
    transition authority refuses and zero writes occur."""
    invoice_id = _seed(app, approver_role="manager")
    _call_submit(app, invoice_id)
    _call_decide(app, invoice_id, action="approve", role=ROLE_MANAGER)
    before = _snapshot(app, invoice_id)
    for action in ("approve", "reject"):
        result = _call_decide(app, invoice_id, action=action,
                              role=ROLE_MANAGER, reason="again")
        assert result["ok"] is False and result["error_kind"] == "invalid"
    assert _snapshot(app, invoice_id) == before


def test_reject_then_second_decision_refused(app):
    invoice_id = _seed(app)
    _call_submit(app, invoice_id)
    _call_decide(app, invoice_id, action="reject", role=ROLE_MANAGER,
                 reason="Duplicate of #12")
    before = _snapshot(app, invoice_id)
    result = _call_decide(app, invoice_id, action="approve", role=ROLE_MANAGER)
    assert result["ok"] is False and result["error_kind"] == "invalid"
    assert _snapshot(app, invoice_id) == before


def test_decide_for_missing_record(app):
    result = _call_decide(app, 9999, action="approve", role=ROLE_MANAGER)
    assert result["ok"] is False and result["error_kind"] == "missing"


# ------------------------------------------------- queue query (§3.2)

def test_list_pending_for_role_filters_by_routing(app):
    mine = _seed(app, invoice_number="INV-MINE", total="108.00")        # manager
    theirs = _seed(app, invoice_number="INV-THEIRS", total="150000.00")  # finance
    _call_submit(app, mine)
    _call_submit(app, theirs)
    with app.app_context():
        from app.db.repository import list_pending_for_role

        conn = get_db()
        try:
            manager_rows = list_pending_for_role(conn, "manager")
            finance_rows = list_pending_for_role(conn, "finance")
        finally:
            conn.close()
    assert [row["id"] for row in manager_rows] == [mine]
    assert [row["id"] for row in finance_rows] == [theirs]


def test_list_pending_excludes_non_pending(app):
    completed = _seed(app, status="completed")
    approved = _seed(app, status="approved", approver_role="manager")
    with app.app_context():
        from app.db.repository import list_pending_for_role

        conn = get_db()
        try:
            rows = list_pending_for_role(conn, "manager")
        finally:
            conn.close()
    assert completed not in [row["id"] for row in rows]
    assert approved not in [row["id"] for row in rows]


# --------------------------------------------------------------- helpers

def _event_names(app, invoice_id):
    conn = _conn(app)
    try:
        return [
            row[0] for row in conn.execute(
                "SELECT event_type FROM invoice_audit WHERE invoice_id = ? "
                "ORDER BY id", (invoice_id,)
            ).fetchall()
        ]
    finally:
        conn.close()


def _last_details(app, invoice_id):
    conn = _conn(app)
    try:
        return conn.execute(
            "SELECT details FROM invoice_audit WHERE invoice_id = ? "
            "ORDER BY id DESC LIMIT 1", (invoice_id,)
        ).fetchone()[0]
    finally:
        conn.close()


def _actor_of_last(app, invoice_id):
    conn = _conn(app)
    try:
        return conn.execute(
            "SELECT actor FROM invoice_audit WHERE invoice_id = ? "
            "ORDER BY id DESC LIMIT 1", (invoice_id,)
        ).fetchone()[0]
    finally:
        conn.close()
