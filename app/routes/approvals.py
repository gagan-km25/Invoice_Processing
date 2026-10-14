"""Approval queue and decisions — Sprint E4 (ARCHITECTURE §6 route map).

Thin HTTP layer: guards, flash, redirect. Guards, routing, and legality
live in app/services (roles/approvals/workflow); all SQL in the
repository. Wrong-role attempts are 403 with zero database writes; state
or reason problems flash an error and redirect with zero writes.
"""
from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from app.db import get_db
from app.db.repository import list_pending_for_role
from app.services import approvals
from app.services.roles import approver_role_for, current_role

bp = Blueprint("approvals", __name__)


@bp.get("/approvals")
def queue():
    """The session role's approval queue; vendors get 403 (route map)."""
    approver_role = approver_role_for(current_role())
    if approver_role is None:
        abort(403)
    conn = get_db()
    try:
        rows = list_pending_for_role(conn, approver_role)
    finally:
        conn.close()
    return render_template("approvals.html", rows=rows, role=current_role())


@bp.post("/invoices/<int:invoice_id>/approve")
def approve(invoice_id: int):
    return _decide(invoice_id, "approve")


@bp.post("/invoices/<int:invoice_id>/reject")
def reject(invoice_id: int):
    return _decide(invoice_id, "reject", reason=request.form.get("reason"))


def _decide(invoice_id: int, action: str, reason: str | None = None):
    """Apply one decision: forbidden → 403 (no writes); invalid → flash +
    redirect (no writes); success → flash + redirect."""
    conn = get_db()
    try:
        result = approvals.decide(
            conn, invoice_id, action=action, role=current_role(), reason=reason
        )
    finally:
        conn.close()
    if not result["ok"]:
        if result["error_kind"] == "forbidden":
            abort(403)
        flash(result["error"], "error")
        return redirect(url_for("invoices.detail", invoice_id=invoice_id))
    past_tense = "approved" if action == "approve" else "rejected"
    flash(f"Record #{invoice_id} {past_tense}.", "success")
    return redirect(url_for("invoices.detail", invoice_id=invoice_id))
