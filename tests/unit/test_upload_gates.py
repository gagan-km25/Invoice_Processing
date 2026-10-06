"""Sprint 1 unit tests — upload gate sequence (plan S1-T6).

Each test drives store_upload() directly inside an app context and checks the
gate's stable error code. Case IDs: TC-S1-U01 … TC-S1-U16 (catalogued in
docs/04-test-results.md).
"""
import shutil
from hashlib import sha256

import pytest

from app.db.repository import get_invoice
from app.services.uploading import UploadRejected, store_upload


def test_valid_pdf_is_stored(app_context, pdf_storage):
    """TC-S1-U01 — valid PDF passes all gates; file + DB row created."""
    storage = pdf_storage("invoice.pdf", pages=1)
    invoice = store_upload(storage)

    assert invoice["status"] == "uploaded"
    assert invoice["original_filename"] == "invoice.pdf"
    assert invoice["page_count"] == 1
    # Safe server-side name: hex UUID + .pdf (nothing client-controlled).
    assert invoice["stored_filename"].endswith(".pdf")
    stem = invoice["stored_filename"][:-4]
    assert len(stem) == 32 and all(c in "0123456789abcdef" for c in stem)
    # File exists in uploads/ and its content hash matches the record.
    stored_path = app_context.config["UPLOAD_DIR"] / invoice["stored_filename"]
    assert stored_path.exists()
    assert invoice["file_hash"] == sha256(stored_path.read_bytes()).hexdigest()


def test_missing_file_rejected(app_context):
    """TC-S1-U02 — no file part at all."""
    with pytest.raises(UploadRejected) as excinfo:
        store_upload(None)
    assert excinfo.value.code == "missing"


def test_empty_filename_rejected(app_context, pdf_storage):
    """TC-S1-U03 — file part present but browser sent no filename."""
    storage = pdf_storage("invoice.pdf")
    storage.filename = ""
    with pytest.raises(UploadRejected) as excinfo:
        store_upload(storage)
    assert excinfo.value.code == "missing"


def test_zero_byte_file_rejected(app_context, pdf_storage):
    """TC-S1-U04 — 0-byte file (E-1)."""
    storage = pdf_storage(name="empty.pdf", data=b"")
    with pytest.raises(UploadRejected) as excinfo:
        store_upload(storage)
    assert excinfo.value.code == "empty"


def test_non_pdf_extension_rejected(app_context, pdf_storage):
    """TC-S1-U05 — .txt file."""
    storage = pdf_storage(name="notes.txt", data=b"plain text, not a pdf")
    with pytest.raises(UploadRejected) as excinfo:
        store_upload(storage)
    assert excinfo.value.code == "extension"


def test_uppercase_pdf_extension_accepted(app_context, pdf_storage):
    """TC-S1-U06 — .PDF / mixed case is still a PDF extension."""
    invoice = store_upload(pdf_storage("Invoice.PDF", pages=1))
    assert invoice["status"] == "uploaded"


def test_renamed_executable_rejected(app_context, pdf_storage):
    """TC-S1-U07 — executable renamed to .pdf fails the magic-byte gate (E-5)."""
    storage = pdf_storage(name="setup.pdf", data=b"MZ\x90\x00fake windows executable")
    with pytest.raises(UploadRejected) as excinfo:
        store_upload(storage)
    assert excinfo.value.code == "magic"


def test_renamed_html_rejected(app_context, pdf_storage):
    """TC-S1-U08 — HTML renamed to .pdf fails the magic-byte gate (stored-XSS vector)."""
    storage = pdf_storage(name="page.pdf", data=b"<html><script>alert(1)</script></html>")
    with pytest.raises(UploadRejected) as excinfo:
        store_upload(storage)
    assert excinfo.value.code == "magic"


def test_corrupt_pdf_rejected(app_context, pdf_storage):
    """TC-S1-U09 — starts like a PDF but is garbage inside (E-2)."""
    storage = pdf_storage(name="broken.pdf", data=b"%PDF-1.4\n>>> not a pdf at all <<<")
    with pytest.raises(UploadRejected) as excinfo:
        store_upload(storage)
    assert excinfo.value.code == "read_error"


def test_oversize_file_rejected(app_context, pdf_storage):
    """TC-S1-U10 — file over the configured size limit."""
    app_context.config["MAX_CONTENT_LENGTH"] = 100  # shrink limit for the test
    storage = pdf_storage(name="big.pdf", data=b"%PDF-" + b"x" * 200)
    with pytest.raises(UploadRejected) as excinfo:
        store_upload(storage)
    assert excinfo.value.code == "size"


def test_encrypted_pdf_rejected(app_context, pdf_storage, monkeypatch):
    """TC-S1-U11 — password-protected PDF gets its own message (E-3).

    The gate under test is our handling of `pdf.is_encrypted`; pdfplumber is
    replaced with a minimal fake so this is deterministic without an
    encryption library.
    """

    class FakeEncryptedPdf:
        is_encrypted = True
        pages = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        "app.services.uploading.pdfplumber.open",
        lambda *args, **kwargs: FakeEncryptedPdf(),
    )
    with pytest.raises(UploadRejected) as excinfo:
        store_upload(pdf_storage("locked.pdf", pages=1))
    assert excinfo.value.code == "encrypted"


def test_page_limit_rejected(app_context, make_pdf, pdf_storage):
    """TC-S1-U12 — real 51-page PDF exceeds the 50-page limit (E-6)."""
    _, pdf_bytes = make_pdf("thick.pdf", pages=51)
    storage = pdf_storage(name="thick.pdf", data=pdf_bytes)
    with pytest.raises(UploadRejected) as excinfo:
        store_upload(storage)
    assert excinfo.value.code == "pagecount"


def test_page_limit_boundary_accepted(app_context, make_pdf, pdf_storage):
    """TC-S1-U12b — exactly 50 pages is within the limit."""
    _, pdf_bytes = make_pdf("boundary.pdf", pages=50)
    invoice = store_upload(pdf_storage(name="boundary.pdf", data=pdf_bytes))
    assert invoice["page_count"] == 50


def test_traversal_filename_stored_safely(app_context, pdf_storage):
    """TC-S1-U13 — unsafe filename is metadata only; traversal impossible."""
    evil_name = "../../evil.pdf"
    invoice = store_upload(pdf_storage(name=evil_name, pages=1))

    assert invoice["original_filename"] == evil_name  # kept as data, not path
    uploads = app_context.config["UPLOAD_DIR"]
    stored_path = uploads / invoice["stored_filename"]
    assert stored_path.exists()
    assert stored_path.parent == uploads  # never outside uploads/
    # Nothing was written next to uploads/ (i.e. no traversal happened).
    outside = uploads.parent / "evil.pdf"
    assert not outside.exists()


def test_upload_dir_recreated_when_missing(app_context, pdf_storage):
    """TC-S1-U14 — deleted uploads dir is recreated on demand (E-25)."""
    shutil.rmtree(app_context.config["UPLOAD_DIR"])
    invoice = store_upload(pdf_storage("after-delete.pdf", pages=1))
    assert (app_context.config["UPLOAD_DIR"] / invoice["stored_filename"]).exists()


def test_rejected_upload_stores_nothing(app_context, pdf_storage, db_rows):
    """TC-S1-U15 — every failed gate leaves no file and no DB row."""
    storage = pdf_storage(name="notes.txt", data=b"not a pdf")
    with pytest.raises(UploadRejected):
        store_upload(storage)
    assert db_rows() == []
    assert list(app_context.config["UPLOAD_DIR"].glob("*")) == []


def test_hash_is_indexed_for_duplicates(app_context, pdf_storage):
    """TC-S1-U16 — same bytes twice: two rows share one file_hash (FR-15)."""
    first = store_upload(pdf_storage("one.pdf", pages=1))
    second = store_upload(pdf_storage("two.pdf", pages=1))  # factory = same bytes
    assert first["file_hash"] == second["file_hash"]
    assert first["id"] != second["id"]
    # And the repository finds the first from the second's hash.
    from app.db import get_db
    from app.db.repository import find_by_hash

    conn = get_db()
    try:
        dupes = find_by_hash(conn, second["file_hash"], exclude_id=second["id"])
    finally:
        conn.close()
    assert [row["id"] for row in dupes] == [first["id"]]
