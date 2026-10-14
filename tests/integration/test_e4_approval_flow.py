"""Sprint E4 integration tests — approval workflow over HTTP
(assignment §10/§11, ARCHITECTURE §6 route map).

The pipeline runs with `extraction.extract_stored_invoice` stubbed so
drafts (and therefore routed amounts) are deterministic. Zero-write proof
for every refusal: direct database reads of the status, decision columns,
AND audit row counts — never the HTTP status alone.
"""
import io
import json
import sqlite3

from app.db import get_db
from app.services import extraction
from app.services.roles import ROLE_FINANCE, ROLE_MANAGER, ROLE_VENDOR


def _field(value):
    return {"status": "found", "value": value}


def _draft(total="108.00", **field_overrides):
    fields = {
        "invoice_number": _field("INV-E4-FLOW"),
        "invoice_date": _field("2026-09-30"),
        "vendor": _field("Acme Corporation"),
        "currency": _field("USD"),
        "subtotal": _field("100.00"),
        "tax": _field("8.00"),
        "total": _field(total),
    }
    fields.update(field_overrides)
    return {
        "fields": fields,
        "lines": [{"line_number": 1, "description": "Widget",
                   "quantity": "2", "unit_price": "50.00",
                   "amount": "100.00", "tax": None}],
        "checks": [],
        "meta": {"page_count": 1, "parser_version": 1, "source": "stub"},
    }


def _stub(monkeypatch, drafts):
    drafts = list(drafts)

    def fake(invoice_id):
        draft = drafts.pop(0)
        conn = get_db()
        try:
            from app.db.repository import update_extraction

            update_extraction(conn, invoice_id, draft=draft, write_lines=True)
        finally:
            conn.close()
        return True, "stubbed"

    monkeypatch.setattr(extraction, "extract_stored_invoice", fake)


def _upload(client, pdf_storage, name="e4.pdf"):
    storage = pdf_storage(name)
    return client.post(
        "/upload",
        data={"file": (io.BytesIO(storage.read()), name)},
        content_type="multipart/form-data",
    )


def _conn(app):
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    return conn


def _row(app, invoice_id):
    conn = _conn(app)
    try:
        return conn.execute(
            "SELECT * FROM invoices WHERE id = ?", (invoice_id,)
        ).fetchone()
    finally:
        conn.close()


def _audit_count(app, invoice_id):
    conn = _conn(app)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM invoice_audit WHERE invoice_id = ?",
            (invoice_id,),
        ).fetchone()[0]
    finally:
        conn.close()


def _events(app, invoice_id):
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


def _invoice_count(app):
    conn = _conn(app)
    try:
        return conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
    finally:
        conn.close()


# ------------------------------------------------- §10: submission (§10)

def test_submit_routes_manager_and_audits(
    app, client, worker, pdf_storage, monkeypatch
):
    """TC-APPR-SUB-01 — vendor submits a completed invoice below the
    threshold: pending_approval, manager routing, both audits."""
    _stub(monkeypatch, [_draft()])
    _upload(client, pdf_storage)
    assert worker.run_pending() == 1
    assert _row(app, 1)["status"] == "completed"

    response = client.post("/invoices/1/submit")
    assert response.status_code == 302
    row = _row(app, 1)
    assert row["status"] == "pending_approval"
    assert row["approver_role"] == "manager"
    assert _events(app, 1)[-2:] == ["review_submitted", "approval_assigned"]


def test_submit_routes_finance_at_high_amounts(
    app, client, worker, pdf_storage, monkeypatch
):
    """TC-APPR-SUB-02 — total ≥ ₹1,00,000 routes to finance."""
    _stub(monkeypatch, [_draft(total="150000.00",
                               subtotal=_field("140000.00"),
                               tax=_field("10000.00"))])
    _upload(client, pdf_storage)
    worker.run_pending()
    client.post("/invoices/1/submit")
    assert _row(app, 1)["approver_role"] == "finance"


def test_submit_null_total_refused_with_message(
    app, client, worker, pdf_storage, monkeypatch
):
    """TC-APPR-SUB-03 — a validation-failed invoice without a total is
    refused (never defaulted to Finance); zero writes."""
    bad = _draft()
    bad["fields"].pop("total")
    _stub(monkeypatch, [bad])
    _upload(client, pdf_storage)
    worker.run_pending()
    assert _row(app, 1)["status"] == "validation_failed"

    before = _audit_count(app, 1)
    response = client.post("/invoices/1/submit", follow_redirects=True)
    assert b"cannot be routed" in response.data
    assert _row(app, 1)["status"] == "validation_failed"
    assert _row(app, 1)["approver_role"] is None
    assert _audit_count(app, 1) == before


def test_double_submit_refused_zero_writes(
    app, client, worker, pdf_storage, monkeypatch
):
    """TC-APPR-SUB-04 — submitting a pending invoice again is refused;
    the audit trail does not grow."""
    _stub(monkeypatch, [_draft()])
    _upload(client, pdf_storage)
    worker.run_pending()
    client.post("/invoices/1/submit")
    before = _audit_count(app, 1)
    response = client.post("/invoices/1/submit", follow_redirects=True)
    assert b"only completed or validation-failed" in response.data
    assert _row(app, 1)["status"] == "pending_approval"
    assert _audit_count(app, 1) == before


# ------------------------------------------------- role matrix (§3/§6)

def test_queue_is_role_filtered(app, client, worker, pdf_storage,
                                monkeypatch, set_role):
    """The manager queue lists only manager-routed invoices; the vendor
    gets 403. Assertions use the queue-row link (not `#N`, which also
    appears in leftover flash messages)."""
    _stub(monkeypatch, [_draft(), _draft(total="150000.00",
                                         subtotal=_field("140000.00"),
                                         tax=_field("10000.00"))])
    _upload(client, pdf_storage, "first.pdf")
    worker.run_pending()
    _upload(client, pdf_storage, "second.pdf")
    worker.run_pending()
    client.post("/invoices/1/submit")
    client.post("/invoices/2/submit")

    assert client.get("/approvals").status_code == 403  # vendor

    set_role(ROLE_FINANCE)
    body = client.get("/approvals").data
    manager_cell = b'href="/invoices/1">#1</a>'
    finance_cell = b'href="/invoices/2">#2</a>'
    assert finance_cell in body and manager_cell not in body

    set_role(ROLE_MANAGER)
    body = client.get("/approvals").data
    assert manager_cell in body and finance_cell not in body


def test_approvers_cannot_use_vendor_actions(
    app, client, worker, pdf_storage, monkeypatch, set_role
):
    """TC-ROLE — upload/review/save/reprocess/delete are vendor actions:
    an approver gets 403 and the database is untouched (upload creates no
    row at all)."""
    set_role(ROLE_MANAGER)
    assert client.get("/").status_code in (200, 302)  # home stays reachable

    rows_before = _invoice_count(app)
    response = client.post(
        "/upload",
        data={"file": (io.BytesIO(b"%PDF-1.4\n"), "x.pdf")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 403
    assert _invoice_count(app) == rows_before  # nothing stored

    # seed one completed invoice as the vendor for the remaining guards
    set_role(ROLE_VENDOR)
    _stub(monkeypatch, [_draft()])
    _upload(client, pdf_storage)
    worker.run_pending()
    set_role(ROLE_MANAGER)

    audits_before = _audit_count(app, 1)
    status_before = _row(app, 1)["status"]

    assert client.get("/invoices/1/review").status_code == 403
    save = client.post("/invoices/1/save", data={"invoice_number": "X"})
    assert save.status_code == 403
    assert _row(app, 1)["status"] == status_before  # zero writes
    reprocess = client.post("/invoices/1/reprocess")
    assert reprocess.status_code == 403
    delete = client.post("/invoices/1/delete", data={"confirm_delete": "1"})
    assert delete.status_code == 403
    assert _row(app, 1) is not None  # not deleted
    assert _audit_count(app, 1) == audits_before  # zero audit writes


# ---------------------------------------------- §11: decisions (§11)

def _pending(app, client, worker, pdf_storage, monkeypatch, total="108.00"):
    _stub(monkeypatch, [_draft(total=total)])
    _upload(client, pdf_storage)
    worker.run_pending()
    client.post("/invoices/1/submit")
    return 1


def test_mismatched_approver_gets_403_with_zero_writes(
    app, client, worker, pdf_storage, monkeypatch, set_role
):
    """TC-APPR-ACT-01 — finance acting on a manager-routed invoice:
    403 and the audit trail does not move."""
    invoice_id = _pending(app, client, worker, pdf_storage, monkeypatch)
    set_role(ROLE_FINANCE)
    before = _audit_count(app, invoice_id)
    response = client.post(f"/invoices/{invoice_id}/approve")
    assert response.status_code == 403
    assert _row(app, invoice_id)["status"] == "pending_approval"
    assert _audit_count(app, invoice_id) == before


def test_vendor_cannot_approve_zero_writes(
    app, client, worker, pdf_storage, monkeypatch
):
    invoice_id = _pending(app, client, worker, pdf_storage, monkeypatch)
    before = _audit_count(app, invoice_id)
    response = client.post(f"/invoices/{invoice_id}/approve")
    assert response.status_code == 403
    assert _audit_count(app, invoice_id) == before
    assert _row(app, invoice_id)["status"] == "pending_approval"


def test_matching_approver_approves(
    app, client, worker, pdf_storage, monkeypatch, set_role
):
    """TC-APPR-ACT-02 — the routed role approves: approved, acted_by/at,
    one audit entry, and a posted reason is never stored."""
    invoice_id = _pending(app, client, worker, pdf_storage, monkeypatch)
    set_role(ROLE_MANAGER)
    response = client.post(f"/invoices/{invoice_id}/approve",
                           data={"reason": "should be ignored"},
                           follow_redirects=True)
    assert response.status_code == 200
    row = _row(app, invoice_id)
    assert row["status"] == "approved"
    assert row["acted_by"] == ROLE_MANAGER
    assert row["acted_at"]
    assert row["rejection_reason"] is None
    assert _events(app, invoice_id)[-1] == "invoice_approved"


def test_approve_from_terminal_state_refused_zero_writes(
    app, client, worker, pdf_storage, monkeypatch, set_role
):
    """TC-APPR-ACT-03 — Approved → Approved / → Rejected are refused by
    the transition authority with zero writes (assignment §11)."""
    invoice_id = _pending(app, client, worker, pdf_storage, monkeypatch)
    set_role(ROLE_MANAGER)
    client.post(f"/invoices/{invoice_id}/approve")
    before = _audit_count(app, invoice_id)
    for action in ("approve", "reject"):
        response = client.post(
            f"/invoices/{invoice_id}/{action}",
            data={"reason": "again"},
            follow_redirects=True,
        )
        assert b"only pending_approval" in response.data
    assert _row(app, invoice_id)["status"] == "approved"
    assert _audit_count(app, invoice_id) == before


def test_reject_requires_reason_zero_writes(
    app, client, worker, pdf_storage, monkeypatch, set_role
):
    """TC-APPR-REJ-01 — a missing/blank reason is refused; nothing moves."""
    invoice_id = _pending(app, client, worker, pdf_storage, monkeypatch)
    set_role(ROLE_MANAGER)
    before = _audit_count(app, invoice_id)
    for reason in (None, "", "   "):
        response = client.post(
            f"/invoices/{invoice_id}/reject",
            data={"reason": reason} if reason is not None else {},
            follow_redirects=True,
        )
        assert b"reason is required" in response.data
    assert _row(app, invoice_id)["status"] == "pending_approval"
    assert _audit_count(app, invoice_id) == before


def test_reject_stores_and_displays_reason(
    app, client, worker, pdf_storage, monkeypatch, set_role
):
    """TC-APPR-REJ-02 — reject with a reason: stored, audited, displayed,
    acted_by/at recorded; a second decision is refused."""
    invoice_id = _pending(app, client, worker, pdf_storage, monkeypatch)
    set_role(ROLE_MANAGER)
    response = client.post(
        f"/invoices/{invoice_id}/reject",
        data={"reason": "Duplicate of record #9"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    row = _row(app, invoice_id)
    assert row["status"] == "rejected"
    assert row["rejection_reason"] == "Duplicate of record #9"
    assert row["acted_by"] == ROLE_MANAGER
    assert _events(app, invoice_id)[-1] == "invoice_rejected"
    assert b"Duplicate of record #9" in response.data  # displayed

    before = _audit_count(app, invoice_id)
    again = client.post(f"/invoices/{invoice_id}/approve")
    assert again.status_code == 302  # refused with a flash, not 403
    assert _row(app, invoice_id)["status"] == "rejected"
    assert _audit_count(app, invoice_id) == before


# --------------------------------------------------- session switching

def test_session_role_switch_round_trip(client, set_role):
    """POST /session/role switches the session; unknown roles are refused
    (400) and leave the role unchanged."""
    set_role(ROLE_MANAGER)
    page = client.get("/approvals")  # 200 once manager, 404-less route
    assert page.status_code == 200

    response = client.post("/session/role", data={"role": "emperor"})
    assert response.status_code == 400
    assert client.get("/approvals").status_code == 200  # still manager

    set_role(ROLE_VENDOR)
    assert client.get("/approvals").status_code == 403


def test_full_lifecycle_walk(
    app, client, worker, pdf_storage, monkeypatch, set_role
):
    """Upload → completed → submitted → approved → further actions
    refused: the assignment §12 lifecycle end-to-end."""
    _stub(monkeypatch, [_draft()])
    _upload(client, pdf_storage)
    worker.run_pending()
    client.post("/invoices/1/submit")
    set_role(ROLE_MANAGER)
    client.post("/invoices/1/approve")
    assert _row(app, 1)["status"] == "approved"

    before = _audit_count(app, 1)
    client.post("/invoices/1/reject", data={"reason": "late"})
    client.post("/invoices/1/submit")
    assert _row(app, 1)["status"] == "approved"
    assert _audit_count(app, 1) == before
