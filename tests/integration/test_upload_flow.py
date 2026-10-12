"""Sprint 1 integration tests — upload flow over HTTP via the Flask test
client (plan S1-T7). Case IDs: TC-S1-I01 … TC-S1-I10 (catalogued in
docs/04-test-results.md).
"""
import io
import shutil
import sqlite3

from app.config import Config


def test_valid_upload_round_trip(app, client, worker, make_pdf):
    """TC-S1-I01 — valid PDF: redirect, success flash, file + row stored.
    Since Sprint E1 the upload returns BEFORE processing; a text-less PDF
    then fails asynchronously with the specific scan message."""
    _, pdf_bytes = make_pdf("sample.pdf", pages=1)

    response = client.post(
        "/upload",
        data={"file": (io.BytesIO(pdf_bytes), "sample.pdf")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Uploaded successfully" in response.data

    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM invoices").fetchall()
    finally:
        conn.close()
    assert len(rows) == 1
    assert rows[0]["status"] == "uploaded"  # E1: response precedes processing
    stored = app.config["UPLOAD_DIR"] / rows[0]["stored_filename"]
    assert stored.exists()
    assert stored.read_bytes() == pdf_bytes  # byte-for-byte storage

    worker.run_pending()  # blank PDF → permanent failure (Sprint 5 gate)
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM invoices").fetchall()
    finally:
        conn.close()
    assert rows[0]["status"] == "failed"  # no-text gate (Sprint 5)
    assert "no selectable text" in rows[0]["error_message"]


def test_missing_file_rejected_over_http(app, client, db_rows):
    """TC-S1-I02 — POST with no file field."""
    response = client.post(
        "/upload", data={}, content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"No file was selected" in response.data
    assert db_rows() == []


def test_non_pdf_rejected_over_http(app, client, db_rows):
    """TC-S1-I03 — .txt upload."""
    response = client.post(
        "/upload",
        data={"file": (io.BytesIO(b"plain text"), "notes.txt")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"Unsupported file type" in response.data
    assert db_rows() == []


def test_corrupt_pdf_rejected_over_http(app, client, db_rows):
    """TC-S1-I04 — corrupt PDF."""
    response = client.post(
        "/upload",
        data={"file": (io.BytesIO(b"%PDF-1.4\ngarbage not a pdf"), "broken.pdf")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"could not be read" in response.data
    assert db_rows() == []


def test_oversize_rejected_over_http(app, client, db_rows):
    """TC-S1-I05 — body over MAX_CONTENT_LENGTH (413 backstop → friendly flash)."""
    app.config["MAX_CONTENT_LENGTH"] = 300  # function-scoped app: safe to shrink
    big = b"%PDF-" + b"x" * 1000
    response = client.post(
        "/upload",
        data={"file": (io.BytesIO(big), "big.pdf")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"File is too large" in response.data
    assert db_rows() == []


def test_page_limit_rejected_over_http(app, client, make_pdf, db_rows):
    """TC-S1-I06 — 51-page PDF."""
    _, pdf_bytes = make_pdf("thick.pdf", pages=51)
    response = client.post(
        "/upload",
        data={"file": (io.BytesIO(pdf_bytes), "thick.pdf")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"exceeds the 50-page" in response.data
    assert db_rows() == []


def test_traversal_filename_over_http(app, client, make_pdf):
    """TC-S1-I07 — unsafe filename over HTTP: stored under uploads/ by UUID."""
    _, pdf_bytes = make_pdf("sample.pdf", pages=1)
    response = client.post(
        "/upload",
        data={"file": (io.BytesIO(pdf_bytes), "../../evil.pdf")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert response.status_code == 200
    uploads = app.config["UPLOAD_DIR"]
    stored_files = list(uploads.iterdir())
    assert len(stored_files) == 1
    assert stored_files[0].parent == uploads
    assert stored_files[0].name.endswith(".pdf")
    assert not (uploads.parent / "evil.pdf").exists()


def test_duplicate_upload_warns(app, client, make_pdf, db_rows):
    """TC-S1-I08 — same file twice: non-blocking warning, both stored."""
    _, pdf_bytes = make_pdf("sample.pdf", pages=1)
    first = client.post(
        "/upload",
        data={"file": (io.BytesIO(pdf_bytes), "a.pdf")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    second = client.post(
        "/upload",
        data={"file": (io.BytesIO(pdf_bytes), "b.pdf")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"Uploaded successfully" in first.data
    assert b"was uploaded before" in second.data
    rows = db_rows()
    assert len(rows) == 2
    assert rows[0]["file_hash"] == rows[1]["file_hash"]
    # both jobs were queued and remain pending — dedupe is per invoice id,
    # not per content (same hash, different ids)
    assert app.extensions["invoice_worker"].queued_count() == 2


def test_deleted_uploads_dir_recovered(app, client, make_pdf):
    """TC-S1-I09 — uploads dir deleted between boots is recreated (E-25)."""
    shutil.rmtree(app.config["UPLOAD_DIR"])
    _, pdf_bytes = make_pdf("sample.pdf", pages=1)
    response = client.post(
        "/upload",
        data={"file": (io.BytesIO(pdf_bytes), "sample.pdf")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"Uploaded successfully" in response.data
    assert app.config["UPLOAD_DIR"].exists()
    assert len(list(app.config["UPLOAD_DIR"].iterdir())) == 1


def test_localhost_only_configuration(app):
    """TC-S1-I10 — localhost-only access assumption is locked in config;
    the actual binding is enforced by run.py using these values."""
    assert Config.HOST == "127.0.0.1"
    assert Config.HOST != "0.0.0.0"
    assert app.config["MAX_CONTENT_LENGTH"] == 10 * 1024 * 1024
