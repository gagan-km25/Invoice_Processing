"""Extraction service: stored file → pdfplumber two-view → parser → database.

Synchronous in-request execution (decision T-F): files are ≤10 MB with a
50-page cap, so worst-case time is bounded. Failure semantics (US-2/NFR-4):
any failure marks the record `failed` with a readable reason — the app never
crashes on a bad file, and the record stays inspectable.
"""
import io
from datetime import datetime, timezone
from pathlib import Path

import pdfplumber
from flask import current_app

from app.db import get_db
from app.db.repository import get_invoice, update_extraction
from app.services import parser


def extract_invoice(invoice_id: int) -> tuple[bool, str]:
    """Run extraction for a stored upload.

    Returns (ok, message): message summarizes the outcome either way, so the
    route can flash it without knowing parser internals.
    """
    conn = get_db()
    try:
        record = get_invoice(conn, invoice_id)
    finally:
        conn.close()
    if record is None:
        return False, f"record #{invoice_id} not found"
    if record["status"] == "failed" and not record["stored_filename"]:
        return False, record["error_message"] or "previous failure"

    file_path = Path(current_app.config["UPLOAD_DIR"]) / record["stored_filename"]
    try:
        data = file_path.read_bytes()
    except OSError as exc:
        _mark_failed(invoice_id, f"stored file could not be read: {exc}")
        return False, "stored file could not be read"

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            page_count = len(pdf.pages)
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            tables = [
                table
                for page in pdf.pages
                for table in (page.extract_tables() or [])
            ]
        draft = parser.parse(text, tables, page_count=page_count)
    except Exception as exc:  # noqa: BLE001 — deliberate failure containment
        _mark_failed(invoice_id, f"extraction error: {exc}")
        return False, "the file could not be processed"

    conn = get_db()
    try:
        update_extraction(conn, invoice_id, draft=draft, status="extracted")
    finally:
        conn.close()
    found = sum(
        1
        for field in draft["fields"].values()
        if field["status"] in ("found", "ambiguous")
    )
    return (
        True,
        f"{found} of {len(draft['fields'])} fields found, "
        f"{len(draft['lines'])} line items",
    )


def _mark_failed(invoice_id: int, message: str) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn = get_db()
    try:
        conn.execute(
            "UPDATE invoices SET status = 'failed', error_message = ?, "
            "updated_at = ? WHERE id = ?",
            (message, now, invoice_id),
        )
        conn.commit()
    finally:
        conn.close()
