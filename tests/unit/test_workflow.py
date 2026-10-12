"""Sprint E0 unit tests: status machine, approval routing, transition writes.

Covers the approved-plan test IDs:
- TC-SM-01..02  every legal transition in TRANSITIONS resolves to its target
- TC-SM-03      illegal transitions return no target / raise InvalidTransition
- TC-SM-04      apply_transition writes status + audit atomically and
                refuses illegal pairs and unknown invoices
- TC-APPR-ROUTE-01..04  approval threshold boundaries (§10: < ₹1,00,000 →
                manager, >= ₹1,00,000 → finance) incl. a custom threshold
"""
from decimal import Decimal

import pytest

from app.db import get_db
from app.db.repository import get_audit, get_invoice, insert_invoice
from app.services import workflow
from app.services.workflow import (
    ACTION_APPROVE,
    ACTION_COMPLETE,
    ACTION_FAIL,
    ACTION_REJECT,
    ACTION_REPROCESS,
    ACTION_START,
    ACTION_SUBMIT,
    ACTION_VALIDATION_FAILED,
    TRANSITIONS,
    InvalidTransition,
    apply_transition,
    required_approver,
    transition_target,
)

# --------------------------------------------------------------------------
# TC-SM-01 — every legal transition resolves to its declared target
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("from_status", "action", "expected"),
    [
        (from_status, action, target)
        for from_status, edges in TRANSITIONS.items()
        for action, target in edges.items()
    ],
)
def test_legal_transitions_resolve(from_status, action, expected):
    assert transition_target(from_status, action) == expected


def test_terminal_states_have_no_outgoing_transitions():
    assert TRANSITIONS["approved"] == {}
    assert TRANSITIONS["rejected"] == {}


# --------------------------------------------------------------------------
# TC-SM-03 — illegal transitions (approved plan: at least 10, incl. the
# assignment §11 examples Approved→Approved and Approved→Rejected)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("from_status", "action"),
    [
        ("uploaded", "approve"),
        ("uploaded", "submit"),
        ("uploaded", "complete"),
        ("uploaded", "reprocess"),
        ("processing", "submit"),
        ("processing", "approve"),
        ("completed", "approve"),
        ("completed", "reprocess"),
        ("pending_approval", "reprocess"),
        ("approved", "approve"),      # Approved → Approved must be blocked
        ("approved", "reject"),       # Approved → Rejected must be blocked
        ("approved", "submit"),
        ("rejected", "reprocess"),
        ("rejected", "submit"),
        ("failed", "submit"),
    ],
)
def test_illegal_transitions_have_no_target(from_status, action):
    assert transition_target(from_status, action) is None


def test_apply_transition_raises_on_illegal_pair(app_context):
    conn = get_db()
    try:
        invoice_id = insert_invoice(
            conn,
            file_hash="h",
            original_filename="a.pdf",
            stored_filename="x.pdf",
            status="approved",
        )
        with pytest.raises(InvalidTransition):
            apply_transition(conn, invoice_id, ACTION_REJECT)
        # nothing changed
        assert get_invoice(conn, invoice_id)["status"] == "approved"
        assert get_audit(conn, invoice_id) == []
    finally:
        conn.close()


# --------------------------------------------------------------------------
# TC-SM-04 — apply_transition writes status + audit in one transaction
# --------------------------------------------------------------------------


def test_apply_transition_writes_status_and_audit(app_context):
    conn = get_db()
    try:
        invoice_id = insert_invoice(
            conn,
            file_hash="h",
            original_filename="a.pdf",
            stored_filename="x.pdf",
            status="uploaded",
        )
        new_status = apply_transition(
            conn, invoice_id, ACTION_START, actor="system"
        )
        assert new_status == "processing"
        record = get_invoice(conn, invoice_id)
        assert record["status"] == "processing"
        entries = get_audit(conn, invoice_id)
        assert len(entries) == 1
        assert entries[0]["event_type"] == "processing_started"
        assert entries[0]["actor"] == "system"
    finally:
        conn.close()


def test_apply_transition_rejects_unknown_invoice(app_context):
    conn = get_db()
    try:
        with pytest.raises(ValueError):
            apply_transition(conn, 9999, ACTION_START)
    finally:
        conn.close()


def test_full_lifecycle_walk(app_context):
    """Walk the documented happy path: uploaded → processing → completed →
    pending_approval → approved, with every step audited exactly once."""
    conn = get_db()
    try:
        invoice_id = insert_invoice(
            conn,
            file_hash="h",
            original_filename="a.pdf",
            stored_filename="x.pdf",
            status="uploaded",
        )
        path = [
            (ACTION_START, "processing", "processing_started"),
            (ACTION_COMPLETE, "completed", "processing_completed"),
            (ACTION_SUBMIT, "pending_approval", "review_submitted"),
            (ACTION_APPROVE, "approved", "invoice_approved"),
        ]
        for action, expected_status, expected_event in path:
            assert apply_transition(conn, invoice_id, action) == expected_status
        entries = get_audit(conn, invoice_id)
        assert [e["event_type"] for e in entries] == [
            expected for _, _, expected in path
        ]
        assert get_invoice(conn, invoice_id)["status"] == "approved"
    finally:
        conn.close()


def test_validation_failed_recovery_path(app_context):
    """validation_failed can be resubmitted after correction, or
    reprocessed back into the pipeline — both routes from the machine."""
    conn = get_db()
    try:
        invoice_id = insert_invoice(
            conn,
            file_hash="h",
            original_filename="a.pdf",
            stored_filename="x.pdf",
            status="processing",
        )
        assert apply_transition(conn, invoice_id, ACTION_VALIDATION_FAILED) == (
            "validation_failed"
        )
        assert apply_transition(conn, invoice_id, ACTION_SUBMIT) == (
            "pending_approval"
        )
    finally:
        conn.close()

    conn = get_db()
    try:
        invoice_id2 = insert_invoice(
            conn,
            file_hash="h2",
            original_filename="b.pdf",
            stored_filename="y.pdf",
            status="processing",
        )
        assert apply_transition(conn, invoice_id2, ACTION_FAIL) == "failed"
        assert apply_transition(conn, invoice_id2, ACTION_REPROCESS) == (
            "processing"
        )
    finally:
        conn.close()


# --------------------------------------------------------------------------
# TC-APPR-ROUTE-01..04 — approval threshold boundary (assignment §10)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("total", "expected"),
    [
        (Decimal("0.00"), "manager"),
        (Decimal("1.00"), "manager"),
        (Decimal("99999.99"), "manager"),   # just below the boundary
        (Decimal("100000.00"), "finance"),  # exactly at the boundary
        (Decimal("100000.01"), "finance"),
        (Decimal("99999999.99"), "finance"),
    ],
)
def test_required_approver_boundaries(total, expected):
    assert required_approver(total, Decimal("100000.00")) == expected


def test_required_approver_respects_custom_threshold():
    assert required_approver(Decimal("50.00"), Decimal("10.00")) == "finance"
    assert required_approver(Decimal("9.99"), Decimal("10.00")) == "manager"


def test_config_threshold_matches_assignment():
    from app.config import Config

    assert Config.APPROVAL_THRESHOLD == Decimal("100000.00")
    assert Config.VALIDATION_TOLERANCE == Decimal("0.01")
    assert len(Config.INVOICE_STATUSES) == 8
    assert set(TRANSITIONS) == set(Config.INVOICE_STATUSES)
