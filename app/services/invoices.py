"""Invoice management service (Sprint 4): safe deletion of saved invoices.

Layering: the route calls this service; the service performs the guard +
repository delete (one committed transaction, lines cascade) and then removes
the stored file best-effort. A missing/locked file never fails the deletion —
the database delete stands and the user is told (AC-06.2).
"""
from pathlib import Path

from flask import current_app

from app.db import get_db
from app.db.repository import delete_invoice, get_invoice


def delete_saved_invoice(invoice_id: int) -> tuple[bool, str]:
    """Delete a saved invoice (and its stored file). Returns (ok, message)
    with a user-facing message either way."""
    conn = get_db()
    try:
        record = get_invoice(conn, invoice_id)
        if record is None:
            return False, f"Invoice {invoice_id} not found."
        if record["status"] != "saved":
            return False, (
                f"Invoice {invoice_id} is {record['status']} — only saved "
                "invoices can be deleted."
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
