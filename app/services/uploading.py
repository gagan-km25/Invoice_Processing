"""Upload gate sequence and secure file storage (Sprint 1; plan S1-T1/T2).

Gates, in order — reject early, say precisely why (US-7):
  1 presence → 2 extension → 3 size → 4 magic bytes →
  5 openability/encryption (PDF) → 6 page count (PDF).

Sprint E2: JPG/JPEG and PNG invoices are accepted alongside PDFs. The
content-signature gate identifies the real type; images skip the PDF-only
page-count gate. The detected type is stored as `invoices.file_type`
('pdf' | 'image') and drives both extraction routing and original-file
serving.

Security posture (requirements §10 / exploration §12):
- The client-supplied filename is never used for storage. Files are stored as
  `<uuid4-hex>.<ext>` inside UPLOAD_DIR, so path traversal is impossible by
  construction; the original name is metadata only.
- Rejected uploads store nothing — no file, no database row.
- This module knows nothing about extraction; status stays `uploaded`.
  (The pipeline calls the extraction service separately.)
"""
import io
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pdfplumber
from flask import current_app

from app.db import get_db
from app.db.repository import get_invoice, insert_invoice

# extension → (content signature, file_type, storage extension)
_SUPPORTED_TYPES = {
    ".pdf": (b"%PDF-", "pdf", ".pdf"),
    ".jpg": (b"\xff\xd8\xff", "image", ".jpg"),
    ".jpeg": (b"\xff\xd8\xff", "image", ".jpg"),
    ".png": (b"\x89PNG\r\n\x1a\n", "image", ".png"),
}


class UploadRejected(Exception):
    """An upload failed a gate. `code` is stable for tests; `user_message`
    names the problem and, where possible, the next step (AC-7.1)."""

    def __init__(self, code: str, user_message: str):
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message


def _mb(limit_bytes: int) -> str:
    return f"{limit_bytes / (1024 * 1024):.0f} MB"


def store_upload(file_storage):
    """Run the gate sequence, store the file, create the DB record.

    Returns the new invoice row. Raises UploadRejected on any failed gate.
    """
    config = current_app.config
    config["UPLOAD_DIR"].mkdir(parents=True, exist_ok=True)  # E-25

    # Gate 1 — presence (browsers submit an empty filename when no file chosen).
    if file_storage is None or not file_storage.filename:
        raise UploadRejected(
            "missing", "No file was selected. Choose a PDF file and try again."
        )

    original_name = file_storage.filename

    # Gate 2 — extension whitelist (cheap check before reading content).
    extension = Path(original_name).suffix.lower()
    if extension not in _SUPPORTED_TYPES:
        raise UploadRejected(
            "extension",
            "Unsupported file type. Only PDF, JPG/JPEG and PNG files are "
            "accepted.",
        )
    signature, file_type, storage_ext = _SUPPORTED_TYPES[extension]

    data = file_storage.stream.read()

    # Gate 3 — size.
    if len(data) == 0:
        raise UploadRejected(
            "empty",
            "The selected file is empty (0 bytes). Choose a valid "
            f"{file_type.upper()} file.",
        )
    max_size = config["MAX_CONTENT_LENGTH"]
    if len(data) > max_size:
        raise UploadRejected(
            "size", f"File is too large. The limit is {_mb(max_size)}."
        )

    # Gate 4 — content signature: catches executables/HTML renamed to an
    # accepted extension (E-5).
    if not data.startswith(signature):
        raise UploadRejected(
            "magic",
            f"This file is not a valid {file_type.upper()} file (its content "
            "does not match the claimed format).",
        )

    page_count = None
    if file_type == "pdf":
        # Gate 5 — openability, encryption. Gate 6 — page count (E-3, E-6).
        try:
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                if getattr(pdf, "is_encrypted", False):
                    raise UploadRejected(
                        "encrypted",
                        "This PDF is password-protected. Save an unprotected "
                        "copy and upload it again.",
                    )
                page_count = len(pdf.pages)
        except UploadRejected:
            raise
        except Exception:
            raise UploadRejected(
                "read_error",
                "The file could not be read as a PDF. It may be corrupt — "
                "try re-saving or exporting it as PDF.",
            ) from None
        if page_count == 0:
            raise UploadRejected(
                "read_error", "The PDF contains no readable pages."
            )
        if page_count > config["PAGE_LIMIT"]:
            raise UploadRejected(
                "pagecount",
                f"This PDF has {page_count} pages, which exceeds the "
                f"{config['PAGE_LIMIT']}-page processing limit.",
            )

    # Safe storage: server-generated name; single-pass SHA-256 for duplicates.
    stored_name = f"{uuid4().hex}{storage_ext}"
    destination = Path(config["UPLOAD_DIR"]) / stored_name
    file_hash = sha256(data).hexdigest()
    destination.write_bytes(data)

    conn = get_db()
    try:
        invoice_id = insert_invoice(
            conn,
            file_hash=file_hash,
            original_filename=original_name,
            stored_filename=stored_name,
            status="uploaded",
            page_count=page_count,
            file_type=file_type,
        )
        return get_invoice(conn, invoice_id)
    finally:
        conn.close()
