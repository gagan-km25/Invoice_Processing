"""Sprint 4 integration tests — history, search, detail, delete over HTTP.
IDs TC-S4-I01… (catalogued in docs/04)."""
import io
import sqlite3
from pathlib import Path

import pytest

from app.db import get_db
from app.services.pipeline import JOB_NEW_UPLOAD
from app.services.review import validate_and_merge
from app.services.uploading import store_upload

def _synthetic(vendor, number, date):
    return [
        "TAX INVOICE",
        f"{vendor} Invoice No: {number}",
        f"1 Main Street, Springfield Invoice Date: {date}",
        "Subtotal $1,000.00",
        "Tax (8%) $80.00",
        "Grand Total $1,080.00",
    ]


def _upload_and_save(client, make_pdf, app, vendor, number, date, name):
    """Upload a synthetic invoice and save it via the review flow. Returns id.
    Since Sprint E1 the worker must run between upload and save."""
    _, pdf_bytes = make_pdf(name, pages=1, text_lines=_synthetic(vendor, number, date))
    client.post(
        "/upload",
        data={"file": (io.BytesIO(pdf_bytes), name)},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    client.application.extensions["invoice_worker"].run_pending()
    invoice_id = _rows(app)[-1]["id"]
    client.post(
        f"/invoices/{invoice_id}/save",
        data={
            "vendor": vendor, "vendor_tax_id": "", "invoice_number": number,
            "invoice_date": date, "due_date": "", "bill_to": "",
            "currency": "USD", "subtotal": "1000.00", "discount": "",
            "tax": "80.00", "tax_rate": "8", "total": "1080.00",
        },
        follow_redirects=True,
    )
    return invoice_id


def _rows(app, query="SELECT * FROM invoices ORDER BY id"):
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(query).fetchall()
    finally:
        conn.close()


# ------------------------------------------------------------- history (S4-01/02)

def test_history_lists_all_statuses_newest_first(app, client, make_pdf):
    """TC-S4-I01 (E5 redefinition) — the list shows ALL statuses, newest
    invoice date first; the status filter narrows it."""
    _upload_and_save(client, make_pdf, app, "Alpha Corp", "INV-A1",
                     "2026-03-01", "a.pdf")
    _upload_and_save(client, make_pdf, app, "Beta GmbH", "INV-B2",
                     "2026-01-01", "b.pdf")
    _upload_and_save(client, make_pdf, app, "Gamma Ltd", "INV-C3",
                     "2026-02-01", "c.pdf")
    _, pdf_bytes = make_pdf("draft.pdf", pages=1, text_lines=_synthetic(
        "Draft Co", "INV-DRAFT", "2026-05-01"))
    client.post("/upload", data={"file": (io.BytesIO(pdf_bytes), "draft.pdf")},
                content_type="multipart/form-data", follow_redirects=True)
    draft_id = _rows(app)[-1]["id"]

    body = client.get("/invoices").data
    for number in (b"INV-A1", b"INV-B2", b"INV-C3"):
        assert number in body  # every status is listed
    # the uploaded draft row appears too (its number is NULL until the
    # worker runs — "INV-DRAFT" has no digits for the parser — so anchor
    # on the row's ID link)
    assert f">#{draft_id}</a>".encode() in body

    filtered = client.get("/invoices", query_string={"status": "completed"}).data
    assert b"INV-A1" in filtered and b"INV-B2" in filtered
    assert f">#{draft_id}</a>".encode() not in filtered  # draft filtered out

    detail = client.get(f"/invoices/{draft_id}")
    assert detail.status_code == 200  # the draft itself is still viewable


def test_history_ordering_exact(app, client, make_pdf):
    """TC-S4-I01b — exact order: newest invoice date first."""
    _upload_and_save(client, make_pdf, app, "Alpha Corp", "INV-A1", "2026-03-01", "a.pdf")
    _upload_and_save(client, make_pdf, app, "Beta GmbH", "INV-B2", "2026-01-01", "b.pdf")
    _upload_and_save(client, make_pdf, app, "Gamma Ltd", "INV-C3", "2026-02-01", "c.pdf")
    body = client.get("/invoices").data
    assert body.index(b"INV-A1") < body.index(b"INV-C3") < body.index(b"INV-B2")


def test_history_summary_columns(app, client, make_pdf):
    """TC-S4-I02 (E5) — ID, number, vendor, date, total, status and
    created date are all rendered (assignment §14)."""
    invoice_id = _upload_and_save(client, make_pdf, app, "Acme Corporation",
                                  "INV-0042", "2026-01-15", "a.pdf")
    body = client.get("/invoices").data
    assert f">#{invoice_id}</a>".encode() in body  # ID column
    assert b"INV-0042" in body
    assert b"Acme Corporation" in body
    assert b"2026-01-15" in body
    assert b"1080.0" in body
    assert b"completed" in body  # status badge
    assert b"Created" in body    # created-date column header


def test_history_empty_state(app, client):
    """TC-S4-I03 — no saved invoices: clear empty state with upload link."""
    response = client.get("/invoices", follow_redirects=True)
    assert b"No invoices yet" in response.data
    assert b"/" in response.data  # upload link present


# ------------------------------------------------------------- search (S4-03)

def test_search_by_number_case_insensitive(app, client, make_pdf):
    """TC-S4-I04 — number fragment, case-insensitive (AC-03.1–3)."""
    _upload_and_save(client, make_pdf, app, "Acme", "INV-0042", "2026-01-15", "a.pdf")
    _upload_and_save(client, make_pdf, app, "Beta", "X-9", "2026-02-15", "b.pdf")
    body = client.get("/invoices", query_string={"q": "inv-00"}).data
    assert b"INV-0042" in body
    assert b"X-9" not in body


def test_search_by_vendor_case_insensitive(app, client, make_pdf):
    """TC-S4-I05 — vendor fragment, case-insensitive."""
    _upload_and_save(client, make_pdf, app, "TechNova Retail", "T-1", "2026-01-15", "a.pdf")
    _upload_and_save(client, make_pdf, app, "Beta", "B-1", "2026-02-15", "b.pdf")
    body = client.get("/invoices", query_string={"q": "technova"}).data
    assert b"TechNova Retail" in body
    assert b"Beta" not in body


def test_search_no_results_state(app, client, make_pdf):
    """TC-S4-I06 — no matches: distinct empty-search message (AC-03.5)."""
    _upload_and_save(client, make_pdf, app, "Acme", "INV-1", "2026-01-15", "a.pdf")
    response = client.get("/invoices", query_string={"q": "zzz"})
    assert b"No invoices match" in response.data


def test_search_percent_is_literal(app, client, make_pdf):
    """TC-S4-I07 — '%' in the search box is a literal character (AC-03.6)."""
    _upload_and_save(client, make_pdf, app, "Acme", "INV-1", "2026-01-15", "a.pdf")
    body = client.get("/invoices", query_string={"q": "%"}).data
    assert b"INV-1" not in body  # wildcard would have matched everything
    assert b"No invoices match" in body


def test_search_underscore_is_literal(app, client, make_pdf):
    """TC-S4-I07b — '_' in the search box is a literal character."""
    _upload_and_save(client, make_pdf, app, "A_B Partners", "AB1", "2026-01-15", "a.pdf")
    _upload_and_save(client, make_pdf, app, "ACX Partners", "ACX1", "2026-02-15", "b.pdf")
    body = client.get("/invoices", query_string={"q": "A_B"}).data
    assert b"A_B Partners" in body
    assert b"ACX Partners" not in body  # wildcard _ would have matched ACX too


def test_search_sql_injection_is_safe(app, client, make_pdf):
    """TC-S4-I18 — SQL meta-characters are inert (AC-R2)."""
    _upload_and_save(client, make_pdf, app, "Acme", "INV-1", "2026-01-15", "a.pdf")
    nasty = "'; DROP TABLE invoices; --"
    response = client.get("/invoices", query_string={"q": nasty})
    assert response.status_code == 200
    rows = _rows(app)
    assert len(rows) == 1  # table intact
    assert rows[0]["invoice_number"] == "INV-1"


def test_pagination_links_and_windows(app, client, make_pdf):
    """TC-S4-I21 — 3 saved invoices at page size 50: one page, count shown;
    paging links appear only when needed (minimal pagination, docs/09)."""
    for i, (v, n, d) in enumerate([
        ("Alpha", "P-1", "2026-03-01"),
        ("Beta", "P-2", "2026-02-01"),
        ("Gamma", "P-3", "2026-01-01"),
    ]):
        _upload_and_save(client, make_pdf, app, v, n, d, f"p{i}.pdf")
    body = client.get("/invoices").data
    assert b"page 1 of 1" in body
    assert b"Older" not in body and b"Newer" not in body


# ------------------------------------------------------------- detail (S4-04)

def test_detail_shows_everything(app, client, make_pdf):
    """TC-S4-I08 — complete header + line items + view original (AC-04.1–3)."""
    invoice_id = _upload_and_save(client, make_pdf, app, "Acme Corporation",
                                  "INV-0042", "2026-01-15", "a.pdf")
    body = client.get(f"/invoices/{invoice_id}").data
    for needle in (b"INV-0042", b"Acme Corporation", b"2026-01-15",
                   b"1000.0", b"80.0", b"1080.0", b"USD", b"completed",
                   b"View original"):
        assert needle in body, needle


def test_detail_unknown_and_nonsaved(app, client, worker, make_pdf):
    """TC-S4-I09 — unknown id → 404; since Sprint E1 the detail page is
    available for every status (processing progress is visible)."""
    assert client.get("/invoices/9999").status_code == 404
    _, pdf_bytes = make_pdf("draft.pdf", pages=1)
    client.post("/upload", data={"file": (io.BytesIO(pdf_bytes), "d.pdf")},
                content_type="multipart/form-data", follow_redirects=True)
    draft_id = _rows(app)[-1]["id"]

    processing = client.get(f"/invoices/{draft_id}")
    assert processing.status_code == 200
    assert b"status-uploaded" in processing.data  # badge shows current status

    worker.run_pending()
    failed = client.get(f"/invoices/{draft_id}")  # blank PDF fails the scan gate
    assert failed.status_code == 200
    assert b"status-failed" in failed.data
    assert b"likely a scan" in failed.data  # failure reason shown on detail


def test_history_detail_links(app, client, make_pdf):
    """TC-S4-I10 — history rows link to detail; detail links back (AC-04.5)."""
    invoice_id = _upload_and_save(client, make_pdf, app, "Acme", "INV-1",
                                  "2026-01-15", "a.pdf")
    history = client.get("/invoices").data
    assert f"/invoices/{invoice_id}".encode() in history
    detail = client.get(f"/invoices/{invoice_id}")
    assert b"Back to history" in detail.data


def test_view_original_serves_pdf(app, client, make_pdf):
    """TC-S4-I20 — original serving: contained, correct content (AC-04.3)."""
    invoice_id = _upload_and_save(client, make_pdf, app, "Acme", "INV-1",
                                  "2026-01-15", "a.pdf")
    response = client.get(f"/invoices/{invoice_id}/original")
    assert response.status_code == 200
    assert response.data.startswith(b"%PDF-")


# ------------------------------------------------------------- delete (S4-05/06)

def test_delete_requires_confirmation_then_deletes(app, client, make_pdf):
    """TC-S4-I11/I12 — unconfirmed POST deletes nothing; confirmed deletes."""
    invoice_id = _upload_and_save(client, make_pdf, app, "Acme", "INV-1",
                                  "2026-01-15", "a.pdf")
    blocked = client.post(f"/invoices/{invoice_id}/delete", data={},
                          follow_redirects=True)
    assert b"This cannot be undone" in blocked.data
    assert b"TN-" not in blocked.data or b"Acme" in blocked.data  # details shown
    assert _rows(app, f"SELECT * FROM invoices WHERE id = {invoice_id}")[0]["id"] == invoice_id

    confirmed = client.post(
        f"/invoices/{invoice_id}/delete",
        data={"confirm_delete": "1"},
        follow_redirects=True,
    )
    assert f"Invoice #{invoice_id} deleted.".encode() in confirmed.data
    assert _rows(app, f"SELECT * FROM invoices WHERE id = {invoice_id}") == []


def test_cascade_and_no_orphans(app, client, make_pdf):
    """TC-S4-I13 — line items cascade-deleted; zero orphans remain (AC-06.1)."""
    invoice_id = _extract_real_001(app)  # real invoice: 3 line items
    saved_form = {
        "vendor": "TechNova Retail Pvt. Ltd.", "vendor_tax_id": "29AABCT1234F1Z5",
        "invoice_number": "TN-2026-1001", "invoice_date": "2026-10-06",
        "due_date": "", "bill_to": "Gagan K M, Bengaluru, Karnataka",
        "currency": "INR", "subtotal": "6550.00", "discount": "0.00",
        "tax": "1179.00", "tax_rate": "18", "total": "7729.00",
    }
    # E5: a completed invoice is deletable without any prior status change
    client.post(f"/invoices/{invoice_id}/save", data=saved_form,
                follow_redirects=True)
    assert _rows(app, f"SELECT status FROM invoices WHERE id = {invoice_id}")[0][
        "status"] == "completed"
    client.post(f"/invoices/{invoice_id}/delete", data={}, follow_redirects=True)
    client.post(f"/invoices/{invoice_id}/delete",
                data={"confirm_delete": "1"}, follow_redirects=True)
    conn = sqlite3.connect(app.config["DATABASE"])
    try:
        lines = conn.execute(
            "SELECT COUNT(*) FROM invoice_lines WHERE invoice_id = ?",
            (invoice_id,)).fetchone()[0]
        orphans = conn.execute(
            "SELECT COUNT(*) FROM invoice_lines WHERE invoice_id NOT IN "
            "(SELECT id FROM invoices)").fetchone()[0]
    finally:
        conn.close()
    assert lines == 0 and orphans == 0


def test_stored_file_removed_on_delete(app, client, make_pdf):
    """TC-S4-I14 — stored PDF removed from uploads/ (AC-06.2); missing tolerated."""
    invoice_id = _upload_and_save(client, make_pdf, app, "Acme", "INV-1",
                                  "2026-01-15", "a.pdf")
    row = _rows(app, f"SELECT * FROM invoices WHERE id = {invoice_id}")[0]
    stored = app.config["UPLOAD_DIR"] / row["stored_filename"]
    assert stored.exists()
    client.post(f"/invoices/{invoice_id}/delete",
                data={"confirm_delete": "1"}, follow_redirects=True)
    assert not stored.exists()

    # missing file: deletion still succeeds with a tolerant message
    invoice_id2 = _upload_and_save(client, make_pdf, app, "Beta", "INV-2",
                                   "2026-02-15", "b.pdf")
    row2 = _rows(app, f"SELECT * FROM invoices WHERE id = {invoice_id2}")[0]
    (app.config["UPLOAD_DIR"] / row2["stored_filename"]).unlink()
    response = client.post(f"/invoices/{invoice_id2}/delete",
                           data={"confirm_delete": "1"}, follow_redirects=True)
    assert b"already missing" in response.data


def test_delete_leaves_others_untouched(app, client, make_pdf):
    """TC-S4-I15 — deleting one invoice leaves the others intact (AC-06.3)."""
    keep = _upload_and_save(client, make_pdf, app, "Keep Co", "K-1",
                            "2026-01-15", "keep.pdf")
    gone = _upload_and_save(client, make_pdf, app, "Gone Co", "G-1",
                            "2026-02-15", "gone.pdf")
    client.post(f"/invoices/{gone}/delete", data={"confirm_delete": "1"},
                follow_redirects=True)
    assert _rows(app, f"SELECT * FROM invoices WHERE id = {keep}")[0]["id"] == keep
    body = client.get("/invoices").data
    assert b"Keep Co" in body and b"Gone Co" not in body


def test_get_delete_is_405(app, client, make_pdf):
    """TC-S4-I16 — GET on the delete URL must never delete (AC-05.4)."""
    invoice_id = _upload_and_save(client, make_pdf, app, "Acme", "INV-1",
                                  "2026-01-15", "a.pdf")
    response = client.get(f"/invoices/{invoice_id}/delete")
    assert response.status_code == 405
    assert _rows(app, f"SELECT * FROM invoices WHERE id = {invoice_id}")[0] is not None


def test_delete_cross_site_origin_403(app, client, make_pdf):
    """TC-S4-I17 — cross-site delete POST rejected with 403 (AC-05.5)."""
    invoice_id = _upload_and_save(client, make_pdf, app, "Acme", "INV-1",
                                  "2026-01-15", "a.pdf")
    response = client.post(
        f"/invoices/{invoice_id}/delete",
        data={"confirm_delete": "1"},
        headers={"Origin": "http://evil.example"},
    )
    assert response.status_code == 403
    assert _rows(app, f"SELECT * FROM invoices WHERE id = {invoice_id}")[0] is not None


def test_delete_blocked_while_uploaded_and_processing(
    app, client, make_pdf
):
    """TC-S4-I22 (E5 redefinition) — deleting is refused while the record
    is `uploaded`; zero writes."""
    _, pdf_bytes = make_pdf("draft.pdf", pages=1, text_lines=[
        "TAX INVOICE", "Acme Invoice No: X-1", "Subtotal $1.00",
        "Grand Total $1.00"])
    client.post("/upload", data={"file": (io.BytesIO(pdf_bytes), "d.pdf")},
                content_type="multipart/form-data", follow_redirects=True)
    draft_id = _rows(app)[-1]["id"]

    while_uploaded = client.post(
        f"/invoices/{draft_id}/delete",
        data={"confirm_delete": "1"}, follow_redirects=True)
    assert b"cannot be deleted while queued or processing" in while_uploaded.data
    assert _rows(app, f"SELECT * FROM invoices WHERE id = {draft_id}")[0] is not None

    # a processing record is equally protected (repository-level proof in
    # tests/unit/test_history_repository.py::test_delete_guard_blocked_states)
    conn = sqlite3.connect(app.config["DATABASE"])
    try:
        conn.execute(
            "UPDATE invoices SET status = 'processing' WHERE id = ?",
            (draft_id,))
        conn.commit()
    finally:
        conn.close()
    while_processing = client.post(
        f"/invoices/{draft_id}/delete",
        data={"confirm_delete": "1"}, follow_redirects=True)
    assert b"cannot be deleted while queued or processing" in while_processing.data
    assert _rows(app, f"SELECT * FROM invoices WHERE id = {draft_id}")[0] is not None


def test_sprint3_regression_review_save_still_works(app, client, make_pdf):
    """TC-S4-I19 (E5) — upload → review → save still works; the record
    stays `completed` and remains listed and reviewable."""
    invoice_id = _upload_and_save(client, make_pdf, app, "Acme", "INV-1",
                                  "2026-01-15", "a.pdf")
    row = _rows(app, f"SELECT * FROM invoices WHERE id = {invoice_id}")[0]
    assert row["status"] == "completed"
    assert row["invoice_number"] == "INV-1"
    review = client.get(f"/invoices/{invoice_id}/review")
    assert review.status_code == 200
    body = client.get("/invoices").data
    assert b"INV-1" in body


def _extract_real_001(app):
    """Extract invoice_001 (3 line items); skips if the sample is absent."""
    samples = Path(__file__).resolve().parents[2] / "sample_invoices"
    sample = samples / "invoice_001_retail.pdf"
    if not sample.exists():
        pytest.skip("sample invoice_001_retail.pdf not present")
    from werkzeug.datastructures import FileStorage
    with app.app_context():
        record = store_upload(FileStorage(io.BytesIO(sample.read_bytes()),
                                          filename=sample.name,
                                          content_type="application/pdf"))
        app.extensions["invoice_worker"].process_job(
            record["id"], JOB_NEW_UPLOAD
        )
        return record["id"]

