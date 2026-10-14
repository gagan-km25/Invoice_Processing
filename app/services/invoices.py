"""Invoice management service (Sprint 4; delete policy rewired Sprint E5).

Layering: the route calls this service; the service performs the guard +
repository delete (one committed transaction, lines and audit cascade) and
then removes the stored file best-effort. A missing/locked file never fails
the deletion — the database delete stands and the user is told (AC-06.2).

Delete policy (Sprint E5, approved decision 1): records still `uploaded`
or `processing` are protected — a queued job owns the former, the pipeline
owns the latter. Every other status is deletable with confirmation.
"""
from pathlib import Path

from flask import current_app

from app.db import get_db
from app.db.repository import delete_invoice, get_invoice

_PROTECTED_MESSAGE = (
    "Invoice #{id} is {status} — it cannot be deleted while queued or "
    "processing."
)


def delete_invoice_record(invoice_id: int) -> tuple[bool, str]:
    """Delete an invoice (and its stored file). Returns (ok, message) with
    a user-facing message either way."""
    conn = get_db()
    try:
        record = get_invoice(conn, invoice_id)
        if record is None:
            return False, f"Invoice {invoice_id} not found."
        if record["status"] in ("uploaded", "processing"):
            return False, _PROTECTED_MESSAGE.format(
                id=invoice_id, status=record["status"]
            )
        stored_filename = record["stored_filename"]
        delete_invoice(conn, invoice_id)
    finally:
        conn.close()

    # Database delete is committed; file removal is best-effort (AC-06.2).
    try:
        (Path(current_app.config["UPLOAD_DIR"]) / stored_filename).unlink()
        return True, f"Invoice #{invoice_id} deleted."
    except FileNotFoundError:
        return True, f"Invoice #{invoice_id} deleted (stored file was already missing)."
    except OSError as exc:
        return (
            True,
            f"Invoice #{invoice_id} deleted, but the stored file could not be "
            f"removed ({exc}).",
        )
