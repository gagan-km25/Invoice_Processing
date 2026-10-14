"""Approval submission and decisions — Sprint E4 (assignment §10/§11).

Orchestration between the workflow authority and the repository:
- `workflow.transition_target` stays the single legality authority (which
  (from_status, action) pairs are legal);
- `workflow.required_approver` stays the single §10 routing rule;
- the repository performs each status + columns + audit write in ONE
  transaction.

Errors are returned, not raised: {ok: False, error_kind, error} where
`error_kind` is "missing" | "invalid" (state/reason problems — flash and
redirect) | "forbidden" (role problems — HTTP 403, zero writes). The
database is only written when every guard passes, so every refusal path
leaves status and audit untouched (verified by tests).
"""
from decimal import Decimal

from app.db.repository import (
    get_invoice,
    record_approval_decision,
    submit_for_approval,
)
from app.services import workflow
from app.services.roles import approver_role_for

NULL_TOTAL_MESSAGE = (
    "This invoice has no total amount yet, so it cannot be routed for "
    "approval — §10 routing requires the invoice amount."
)


def submit(conn, invoice_id: int, *, threshold: Decimal) -> dict:
    """Submit a completed/validation-failed invoice for approval, routing
    it by amount (§10). Refuses NULL totals (approved decision 1: no
    default to Finance) and non-submittable states (approved decision 3:
    `saved` is outside the approval flow)."""
    record = get_invoice(conn, invoice_id)
    if record is None:
        return {
            "ok": False,
            "error_kind": "missing",
            "error": f"Record #{invoice_id} could not be found.",
        }
    if workflow.transition_target(record["status"], workflow.ACTION_SUBMIT) is None:
        return {
            "ok": False,
            "error_kind": "invalid",
            "error": (
                f"Record #{invoice_id} is {record['status']} — only "
                "completed or validation-failed invoices can be submitted "
                "for approval."
            ),
        }
    if record["total"] is None:
        return {"ok": False, "error_kind": "invalid", "error": NULL_TOTAL_MESSAGE}

    amount = Decimal(str(record["total"]))
    approver_role = workflow.required_approver(amount, threshold)
    submit_for_approval(conn, invoice_id, approver_role=approver_role)
    return {"ok": True, "approver_role": approver_role}


def decide(conn, invoice_id: int, *, action: str, role: str,
           reason: str | None = None) -> dict:
    """Approve or reject a pending invoice as the session role.

    Guards, in order: vendor/unknown role → forbidden (§3.2 — only
    approvers act); unknown/mis-routed record → invalid; non-pending
    status → invalid (transition authority); role ≠ `approver_role` →
    forbidden; reject without a non-blank reason → invalid. Only then is
    the one-transaction decision written."""
    approver_role = approver_role_for(role)
    if approver_role is None:
        return {
            "ok": False,
            "error_kind": "forbidden",
            "error": "Only approvers can approve or reject invoices.",
        }
    record = get_invoice(conn, invoice_id)
    if record is None:
        return {
            "ok": False,
            "error_kind": "missing",
            "error": f"Record #{invoice_id} could not be found.",
        }
    if workflow.transition_target(record["status"], action) is None:
        return {
            "ok": False,
            "error_kind": "invalid",
            "error": (
                f"Record #{invoice_id} is {record['status']} — only "
                "pending_approval invoices can be approved or rejected."
            ),
        }
    if record["approver_role"] != approver_role:
        return {
            "ok": False,
            "error_kind": "forbidden",
            "error": (
                f"This invoice is routed to the {record['approver_role']} "
                f"approver — you are acting as {role}."
            ),
        }
    clean_reason = (reason or "").strip()
    if action == workflow.ACTION_REJECT and not clean_reason:
        return {
            "ok": False,
            "error_kind": "invalid",
            "error": "A rejection reason is required.",
        }
    record_approval_decision(
        conn,
        invoice_id,
        decision=action,
        actor=role,
        rejection_reason=clean_reason if action == workflow.ACTION_REJECT else None,
    )
    return {"ok": True}
