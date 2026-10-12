"""Audit event catalogue (enhancement assignment §13; Sprint E0 foundation).

The catalogue documents every lifecycle event the system records. Writes go
through the repository (all SQL lives in app/db/); status changes always
carry their audit entry in the same transaction via
workflow.apply_transition → repository.transition_status.

`actor` is "system" for pipeline/worker/migration events, or the session
role label ("vendor" / "approver:manager" / "approver:finance") for
user actions — a session label, not an authenticated identity (see
docs/ARCHITECTURE.md, role-model limits).
"""

# Upload / processing
EVENT_INVOICE_UPLOADED = "invoice_uploaded"
EVENT_PROCESSING_STARTED = "processing_started"
EVENT_PROCESSING_RESUMED = "processing_resumed"      # recovery job only
EVENT_PROCESSING_COMPLETED = "processing_completed"
EVENT_REPROCESS_REQUESTED = "reprocess_requested"

# Extraction
EVENT_EXTRACTION_COMPLETED = "extraction_completed"
EVENT_EXTRACTION_FAILED = "extraction_failed"

# Validation / duplicates
EVENT_VALIDATION_COMPLETED = "validation_completed"
EVENT_VALIDATION_FAILED = "validation_failed"
EVENT_DUPLICATE_DETECTED = "duplicate_detected"

# Review / approval
EVENT_REVIEW_SUBMITTED = "review_submitted"
EVENT_APPROVAL_ASSIGNED = "approval_assigned"
EVENT_INVOICE_APPROVED = "invoice_approved"
EVENT_INVOICE_REJECTED = "invoice_rejected"

# Migration
EVENT_RECORD_MIGRATED = "record_migrated"

# All event types, for tests and documentation checks.
ALL_EVENTS = (
    EVENT_INVOICE_UPLOADED,
    EVENT_PROCESSING_STARTED,
    EVENT_PROCESSING_RESUMED,
    EVENT_PROCESSING_COMPLETED,
    EVENT_REPROCESS_REQUESTED,
    EVENT_EXTRACTION_COMPLETED,
    EVENT_EXTRACTION_FAILED,
    EVENT_VALIDATION_COMPLETED,
    EVENT_VALIDATION_FAILED,
    EVENT_DUPLICATE_DETECTED,
    EVENT_REVIEW_SUBMITTED,
    EVENT_APPROVAL_ASSIGNED,
    EVENT_INVOICE_APPROVED,
    EVENT_INVOICE_REJECTED,
    EVENT_RECORD_MIGRATED,
)


def record(conn, invoice_id: int, event_type: str, actor: str = "system",
           details: str | None = None) -> int:
    """Record one audit entry (delegates to the repository)."""
    from app.db.repository import insert_audit

    return insert_audit(conn, invoice_id, event_type, actor=actor, details=details)
