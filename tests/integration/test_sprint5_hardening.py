"""Sprint 5 tests — no-text-layer gate, error-path audit, invoice isolation.
IDs TC-S5-* (catalogued in docs/04). Updated for the Sprint E1 async
pipeline: extraction runs via the worker, so tests drive it explicitly."""
import io
import sqlite3

from werkzeug.datastructures import FileStorage

from app.db import get_db
from app.db.repository import get_invoice
from app.services.pipeline import JOB_NEW_UPLOAD
from app.services.uploading import store_upload

NO_TEXT_SNIPPET = "no selectable text"

SYNTHETIC_A = [
    "TAX INVOICE",
    "Acme Corporation Invoice No: INV-ISO-100",
    "1 Main Street, Springfield Invoice Date: 2026-01-15",
    "Subtotal $1,000.00",
    "Grand Total $1,000.00",
]
SYNTHETIC_B = [
    "TAX INVOICE",
    "Beta Industries Invoice No: INV-ISO-200",
    "9 Other Road, Shelbyville Invoice Date: 2026-02-20",
    "Subtotal $2,500.00",
    "Grand Total $2,500.00",
]


def _upload(client, make_pdf, name, text_lines=None, follow=True):
    _, pdf_bytes = make_pdf(name, pages=1, text_lines=text_lines)
    return client.post(
        "/upload",
        data={"file": (io.BytesIO(pdf_bytes), name)},
        content_type="multipart/form-data",
        follow_redirects=follow,
    )


# ------------------------------------------------- US-S5-01: no-text gate

def test_no_text_pdf_fails_with_scan_message(app, worker, make_pdf):
    """TC-S5-U01 — valid PDF, no text: the pipeline fails the record with
    the specific scan message; nothing half-written."""
    _, pdf_bytes = make_pdf("blank.pdf", pages=1)  # valid PDF, no text
    with app.app_context():
        record = store_upload(FileStorage(io.BytesIO(pdf_bytes),
                                          filename="blank.pdf"))
        worker.process_job(record["id"], JOB_NEW_UPLOAD)
        row = get_invoice(get_db(), record["id"])

    assert "likely a scan" in row["error_message"]
    assert row["status"] == "failed"
    assert NO_TEXT_SNIPPET in row["error_message"]


def test_text_pdf_unaffected_by_gate(app, client, worker, make_pdf):
    """TC-S5-U02 — text-bearing PDFs pass the gate unchanged (regression)."""
    response = _upload(client, make_pdf, "with-text.pdf", text_lines=SYNTHETIC_A)
    assert b"Uploaded successfully" in response.data
    worker.run_pending()
    row = _rows(app)[-1]
    assert row["status"] == "completed"
    assert NO_TEXT_SNIPPET not in (row["error_message"] or "")


def test_no_text_pdf_http_flow(app, client, worker, make_pdf):
    """TC-S5-I01 — HTTP upload of a no-text PDF: terminal `failed` status,
    review refused (non-reviewable)."""
    response = _upload(client, make_pdf, "blank.pdf")  # blank page: no text
    assert b"Uploaded successfully" in response.data
    invoice_id = _rows(app)[-1]["id"]
    worker.run_pending()

    row = _rows(app, f"SELECT status, error_message FROM invoices WHERE id = {invoice_id}")[0]
    assert row["status"] == "failed"
    assert NO_TEXT_SNIPPET in row["error_message"]

    review = client.get(f"/invoices/{invoice_id}/review", follow_redirects=True)
    assert b"only extracted or completed invoices can be reviewed" in review.data


def _rows(app, query="SELECT * FROM invoices ORDER BY id"):
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(query).fetchall()
    finally:
        conn.close()


# ------------------------------------------------- US-S5-02: error-path audit

def test_known_error_paths_never_500(app, client, make_pdf, monkeypatch):
    """TC-S5-I03 — every known failure input responds with a handled status
    (< 500) and user-facing messaging; the app stays up throughout (AC-02.1)."""
    # wrong type
    r1 = client.post("/upload", data={"file": (io.BytesIO(b"plain"), "x.txt")},
                     content_type="multipart/form-data", follow_redirects=True)
    # missing file
    r2 = client.post("/upload", data={}, content_type="multipart/form-data",
                     follow_redirects=True)
    # corrupt pdf
    r3 = client.post("/upload", data={"file": (io.BytesIO(b"%PDF-1.4 junk"), "c.pdf")},
                     content_type="multipart/form-data", follow_redirects=True)
    # oversize (limit shrunk for the test)
    monkeypatch.setattr(app, "config", {**app.config, "MAX_CONTENT_LENGTH": 300})
    r4 = client.post("/upload", data={"file": (io.BytesIO(b"%PDF-" + b"x" * 500), "big.pdf")},
                     content_type="multipart/form-data", follow_redirects=True)
    monkeypatch.undo()
    # unknown ids
    r5 = client.get("/invoices/424242")           # 404
    r6 = client.get("/invoices/424242/original")  # 404
    # unknown record delete POST
    r7 = client.post("/invoices/424242/delete", data={"confirm_delete": "1"})
    # GET on delete endpoint
    r8 = client.get("/invoices/1/delete")
    # injection-style search
    r9 = client.get("/invoices", query_string={"q": "'; DROP TABLE invoices; --"})

    for name, response in [("wrong-type", r1), ("missing-file", r2),
                           ("corrupt", r3), ("oversize", r4),
                           ("detail-404", r5), ("original-404", r6),
                           ("delete-unknown", r7), ("get-delete", r8),
                           ("injection-search", r9)]:
        assert response.status_code < 500, (name, response.status_code)
    # app still healthy afterwards
    assert client.get("/").status_code == 200
    assert client.get("/invoices").status_code == 200


# ------------------------------------------------- US-S5-03: isolation

def test_invoice_data_isolation(app, client, worker, make_pdf):
    """TC-S5-I04/I05 — no invoice's values ever appear on another invoice's
    review, detail, or history pages (US-S5-03)."""
    _upload(client, make_pdf, "a.pdf", text_lines=SYNTHETIC_A)
    a_id = _rows(app)[-1]["id"]
    _upload(client, make_pdf, "b.pdf", text_lines=SYNTHETIC_B)
    b_id = _rows(app)[-1]["id"]
    worker.run_pending()  # complete both pipelines before review/save

    a_markers = [b"Acme Corporation", b"INV-ISO-100", b"Springfield"]
    b_markers = [b"Beta Industries", b"INV-ISO-200", b"Shelbyville"]

    review_a = client.get(f"/invoices/{a_id}/review").data
    review_b = client.get(f"/invoices/{b_id}/review").data
    for marker in b_markers:
        assert marker not in review_a, marker
    for marker in a_markers:
        assert marker not in review_b, marker

    # save both, then check detail + history the same way
    for invoice_id, form in (
        (a_id, {"vendor": "Acme Corporation", "invoice_number": "INV-ISO-100",
                "invoice_date": "2026-01-15", "subtotal": "1000.00",
                "total": "1000.00", "currency": "USD", "bill_to": "",
                "vendor_tax_id": "", "due_date": "", "discount": "",
                "tax": "", "tax_rate": ""}),
        (b_id, {"vendor": "Beta Industries", "invoice_number": "INV-ISO-200",
                "invoice_date": "2026-02-20", "subtotal": "2500.00",
                "total": "2500.00", "currency": "USD", "bill_to": "",
                "vendor_tax_id": "", "due_date": "", "discount": "",
                "tax": "", "tax_rate": ""}),
    ):
        saved = client.post(f"/invoices/{invoice_id}/save", data=form,
                            follow_redirects=True)
        assert b"saved" in saved.data

    detail_a = client.get(f"/invoices/{a_id}").data
    detail_b = client.get(f"/invoices/{b_id}").data
    for marker in b_markers + [b"Beta"]:
        assert marker not in detail_a, marker
    for marker in a_markers + [b"Acme"]:
        assert marker not in detail_b, marker

    history = client.get("/invoices").data
    assert b"Acme Corporation" in history and b"Beta Industries" in history
    assert b"INV-ISO-100" in history and b"INV-ISO-200" in history
