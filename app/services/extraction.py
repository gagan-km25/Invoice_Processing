"""Extraction service: stored file → pdfplumber two-view → parser → draft.

Sprint E1 refactor: this module extracts and persists the *draft*; it does
NOT change `invoices.status` — the pipeline (app/services/pipeline.py) owns
every status transition through the workflow machine. Failure semantics:
failures are raised as typed exceptions so the pipeline can distinguish
retryable from permanent and record the terminal state exactly once.

- `ExtractionRetryable`: transient conditions worth re-attempting (e.g. the
  stored file temporarily unreadable — a OneDrive sync hiccup; from E2,
  network/5xx/429 provider errors).
- `ExtractionPermanent`: re-running cannot succeed (invalid/unreadable PDF,
  no text layer / scan, parser poison).

Both carry a `user_message`: a fixed, user-safe string (never exception
text) suitable for `error_message` and flashes. The app never crashes on a
bad file, and the record stays inspectable (US-2/NFR-4, unchanged).
"""
import io
from pathlib import Path

import pdfplumber
from flask import current_app

from app.db import get_db
from app.db.repository import get_invoice, update_extraction
from app.services import parser


class ExtractionError(Exception):
    """Base: extraction failed. `user_message` is always user-safe."""

    def __init__(self, user_message: str):
        self.user_message = user_message
        super().__init__(user_message)


class ExtractionPermanent(ExtractionError):
    """Re-running extraction cannot succeed."""


class ExtractionRetryable(ExtractionError):
    """Transient condition — a bounded retry may succeed."""


def extract_stored_invoice(invoice_id: int) -> tuple[bool, str]:
    """Run extraction for a stored upload and persist the draft.

    Status policy: this function never writes `invoices.status`. On success
    the draft + line items are persisted (`update_extraction`) and
    (True, summary) is returned; on failure an ExtractionRetryable /
    ExtractionPermanent is raised and the pipeline performs the terminal
    transition with `user_message`.
    """
    conn = get_db()
    try:
        record = get_invoice(conn, invoice_id)
    finally:
        conn.close()
    if record is None:
        raise ExtractionPermanent(f"Record #{invoice_id} could not be found.")
    if record["status"] == "failed" and not record["stored_filename"]:
        raise ExtractionPermanent(record["error_message"] or "previous failure")

    file_path = Path(current_app.config["UPLOAD_DIR"]) / record["stored_filename"]
    try:
        data = file_path.read_bytes()
    except OSError:
        # Transient in practice (e.g. OneDrive sync lock) — bounded retry.
        raise ExtractionRetryable(
            "The stored file could not be read right now."
        ) from None

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            page_count = len(pdf.pages)
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            tables = [
                table
                for page in pdf.pages
                for table in (page.extract_tables() or [])
            ]

        # No-text-layer gate (US-S5-01, AC-7.1): a valid PDF with (almost) no
        # selectable text is almost certainly a scan. Fail with the specific
        # message instead of silently producing an all-missing extraction.
        if len(text.strip()) < 20:
            raise ExtractionPermanent(
                "The PDF contains no selectable text — it is likely a scan. "
                "OCR is not available in this version; use a text-based PDF."
            )

        draft = parser.parse(text, tables, page_count=page_count)
    except ExtractionPermanent:
        raise
    except Exception:
        # Contained: never crash, never leak exception text upward. The
        # class name travels via the pipeline's structured log only.
        raise ExtractionPermanent(
            "The file could not be processed — it may be corrupt."
        ) from None

    conn = get_db()
    try:
        update_extraction(conn, invoice_id, draft=draft)  # status unchanged
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
