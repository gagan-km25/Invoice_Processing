"""Invoice lifecycle: the status machine and the approval-routing rule.

Single source of truth for legal status transitions (enhancement assignment
§11/§12; approved plan §2/§C). Nothing anywhere else in the application may
write `invoices.status` directly — every change goes through
`apply_transition`, which validates the (from, action) pair and writes the
status + audit entry atomically via the repository.

Processing status is the only lifecycle state. Validation verdicts,
duplicate classifications, and approval metadata are data columns
(`validation_status`, `dup_status`, `approver_role`, …) — see
docs/ARCHITECTURE.md §State model.

Background-processing note (approved recovery amendment): the worker is the
only caller of ACTION_START / resume logic. A *recovery-designated* job is
the only job permitted to resume an invoice already in `processing`; that
rule lives in the pipeline worker (Sprint E1) — this module stays the pure
transition authority.
"""
from decimal import Decimal

from app.db import repository
from app.db.repository import get_invoice

# --- Actions ---------------------------------------------------------------

ACTION_START = "start"                    # uploaded → processing (worker only)
ACTION_COMPLETE = "complete"              # processing → completed (pipeline)
ACTION_VALIDATION_FAILED = "validation_failed"  # processing → validation_failed
ACTION_FAIL = "fail"                      # processing → failed (pipeline)
ACTION_REPROCESS = "reprocess"            # failed / validation_failed → processing
ACTION_SUBMIT = "submit"                  # completed / validation_failed → pending_approval
ACTION_APPROVE = "approve"                # pending_approval → approved (matching role)
ACTION_REJECT = "reject"                  # pending_approval → rejected (reason required)

# Legal transitions: {from_status: {action: to_status}}. A missing pair is
# an illegal transition (transition_target returns None → InvalidTransition).
TRANSITIONS: dict[str, dict[str, str]] = {
    "uploaded": {ACTION_START: "processing"},
    "processing": {
        ACTION_COMPLETE: "completed",
        ACTION_VALIDATION_FAILED: "validation_failed",
        ACTION_FAIL: "failed",
    },
    "completed": {ACTION_SUBMIT: "pending_approval"},
    "validation_failed": {
        ACTION_SUBMIT: "pending_approval",
        ACTION_REPROCESS: "processing",
    },
    "failed": {ACTION_REPROCESS: "processing"},
    "pending_approval": {ACTION_APPROVE: "approved", ACTION_REJECT: "rejected"},
    "approved": {},   # terminal
    "rejected": {},   # terminal
}

# Audit event recorded with each transition (assignment §13 catalogue).
EVENT_FOR_ACTION = {
    ACTION_START: "processing_started",
    ACTION_COMPLETE: "processing_completed",
    ACTION_VALIDATION_FAILED: "validation_failed",
    ACTION_FAIL: "processing_failed",
    ACTION_REPROCESS: "reprocess_requested",
    ACTION_SUBMIT: "review_submitted",
    ACTION_APPROVE: "invoice_approved",
    ACTION_REJECT: "invoice_rejected",
}

APPROVER_MANAGER = "manager"
APPROVER_FINANCE = "finance"


class InvalidTransition(Exception):
    """Raised for any (from_status, action) pair not in TRANSITIONS."""

    def __init__(self, from_status: str, action: str):
        self.from_status = from_status
        self.action = action
        super().__init__(
            f"invalid transition: {action!r} is not allowed from {from_status!r}"
        )


def transition_target(from_status: str, action: str) -> str | None:
    """Target status for a legal (from, action) pair; None if illegal."""
    return TRANSITIONS.get(from_status, {}).get(action)


def required_approver(total: Decimal, threshold: Decimal) -> str:
    """Assignment §10 routing rule — implemented exactly once, here.

    total <  threshold → manager
    total >= threshold → finance
    """
    return APPROVER_MANAGER if total < threshold else APPROVER_FINANCE


def apply_transition(
    conn,
    invoice_id: int,
    action: str,
    *,
    actor: str = "system",
    details: str | None = None,
) -> str:
    """Validate and perform a status transition (status + audit in one
    transaction). Returns the new status; raises InvalidTransition for an
    illegal pair and ValueError for an unknown invoice. The caller owns the
    connection lifecycle (short-lived, per repository convention)."""
    record = get_invoice(conn, invoice_id)
    if record is None:
        raise ValueError(f"invoice {invoice_id} not found")
    target = transition_target(record["status"], action)
    if target is None:
        raise InvalidTransition(record["status"], action)
    repository.transition_status(
        conn,
        invoice_id,
        new_status=target,
        event_type=EVENT_FOR_ACTION[action],
        actor=actor,
        details=details,
    )
    return target
