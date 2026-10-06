"""Sprint 3 integration tests — review → save over HTTP (temp DB).
IDs TC-S3-I01… (catalogued in docs/04).
"""
import io
import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from werkzeug.datastructures import FileStorage

from app.db import get_db
from app.services.extraction import extract_invoice
from app.services.review import validate_and_merge
from app.services.uploading import store_upload

SAMPLES = Path(__file__).resolve().parents[2] / "sample_invoices"

SYNTHETIC = [
    "TAX INVOICE",
    "Acme Corporation Invoice No: INV-TEST-0001",
    "1 Main Street, Springfield Invoice Date: 2026-01-15",
    "Bill To:",
    "Demo Customer",
    "Springfield",
    "Subtotal $1,000.00",
    "Tax (8%) $80.00",
    "Grand Total $1,080.00",
]


def _upload(client, make_pdf, name="synthetic.pdf", text_lines=None):
    _, pdf_bytes = make_pdf(name, pages=1, text_lines=text_lines or SYNTHETIC)
    return client.post(
        "/upload",
        data={"file": (io.BytesIO(pdf_bytes), name)},
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def _rows(app, query="SELECT * FROM invoices ORDER BY id"):
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(query).fetchall()
    finally:
        conn.close()


def _last_id(app):
    return _rows(app)[-1]["id"]


def _save_form(**overrides):
    form = {
        "vendor": "Acme Corporation",
        "vendor_tax_id": "",
        "invoice_number": "INV-TEST-0001",
        "invoice_date": "2026-01-15",
        "due_date": "",
        "bill_to": "Demo Customer, Springfield",
        "currency": "USD",
        "subtotal": "1000.00",
        "discount": "",
        "tax": "80.00",
        "tax_rate": "8",
        "total": "1080.00",
    }
    form.update(overrides)
    return form


def _save(client, invoice_id, form):
    """Submit the review form for an invoice, following redirects."""
    return client.post(f"/invoices/{invoice_id}/save", data=form,
                       follow_redirects=True)


def _extract_real_001(app):
    """Store + extract invoice_001 (3 line items); skips if sample absent."""
    sample = SAMPLES / "invoice_001_retail.pdf"
    if not sample.exists():
        pytest.skip("sample invoice_001_retail.pdf not present")
    with app.app_context():
        record = store_upload(
            FileStorage(io.BytesIO(sample.read_bytes()),
                        filename=sample.name, content_type="application/pdf")
        )
        extract_invoice(record["id"])
        return record["id"]


# ------------------------------------------------------- review page (US-S3-01)

def test_review_renders_extracted_values(app, client, make_pdf):
    """TC-S3-I01 — upload lands on review; extracted values pre-filled;
    ambiguous/missing fields flagged; Review link on home page."""
    response = _upload(client, make_pdf)
    assert response.status_code == 200
    assert b"Review invoice" in response.data
    assert b"Acme Corporation" in response.data          # prefilled vendor
    assert b"INV-TEST-0001" in response.data             # prefilled number
    assert b"2026-01-15" in response.data                # prefilled date
    assert b"1080.00" in response.data                   # prefilled total
    assert b"not found" in response.data                 # missing-field flags
    invoice_id = _last_id(app)
    home = client.get("/")
    assert f"/invoices/{invoice_id}/review".encode() in home.data


def test_review_unknown_id_404(client):
    """TC-S3-I02 — unknown invoice id → 404."""
    assert client.get("/invoices/9999/review").status_code == 404


def test_review_non_extracted_redirects(app, client, make_pdf):
    """TC-S3-I03 — failed record cannot be reviewed; friendly redirect."""
    _upload(client, make_pdf)                      # creates extracted record 1
    invoice_id = _last_id(app)
    with app.app_context():
        conn = sqlite3.connect(app.config["DATABASE"])
        conn.execute("UPDATE invoices SET status='failed', error_message='x'")
        conn.commit()
        conn.close()
    response = client.get(f"/invoices/{invoice_id}/review", follow_redirects=True)
    assert b"only extracted records can be reviewed" in response.data


# ------------------------------------------------- field editing (US-S3-02)

def test_save_persists_corrections(app, client, make_pdf):
    """TC-S3-I04 — corrected values are what gets stored (AC-02.1)."""
    _upload(client, make_pdf)
    invoice_id = _last_id(app)
    response = _save(client, invoice_id, _save_form(vendor="Acme Corporation (UK)",
                                                    total="1080.55", tax="80.55"))
    assert b"saved" in response.data
    row = _rows(app, f"SELECT * FROM invoices WHERE id = {invoice_id}")[0]
    assert row["vendor"] == "Acme Corporation (UK)"
    assert row["total"] == 1080.55
    assert row["tax"] == 80.55
    assert row["status"] == "saved"


def test_untouched_fields_keep_extraction_values(app, client, make_pdf):
    """TC-S3-I05 — fields not edited persist the extracted values (AC-02.2)."""
    _upload(client, make_pdf)
    invoice_id = _last_id(app)
    _save(client, invoice_id, _save_form())
    row = _rows(app, f"SELECT * FROM invoices WHERE id = {invoice_id}")[0]
    assert row["invoice_number"] == "INV-TEST-0001"
    assert row["invoice_date"] == "2026-01-15"
    assert row["subtotal"] == 1000.00


# ------------------------------------------------- line items (US-S3-03)

def test_line_item_add_edit_remove(app, client, make_pdf):
    """TC-S3-I06 — add a line via a blank row, remove another, edit one
    (real invoice with 3 extracted lines)."""
    invoice_id = _extract_real_001(app)
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    try:
        original = conn.execute(
            "SELECT * FROM invoice_lines WHERE invoice_id = ? ORDER BY line_number",
            (invoice_id,)).fetchall()
    finally:
        conn.close()
    assert len(original) == 3

    form = _save_form(vendor="TechNova Retail Pvt. Ltd.",
                      invoice_number="TN-2026-1001", invoice_date="2026-10-06",
                      subtotal="902.00", tax="0", total="902.00")
    # row 0 (index 0): edit; row 1 (index 1): remove; blank row (index 3): add
    form.update({
        "description_0": "Wireless Keyboard PRO", "quantity_0": "3",
        "unit_price_0": "100.00", "amount_0": "300.00",
        "remove_1": "on",
        "description_1": "", "quantity_1": "", "unit_price_1": "", "amount_1": "",
        "description_3": "New Gadget", "quantity_3": "2",
        "unit_price_3": "301.00", "amount_3": "602.00",
        "description_2": "Laptop Stand", "quantity_2": "1",
        "unit_price_2": "0", "amount_2": "0",
    })
    response = _save(client, invoice_id, form)
    assert b"Invoice #" in response.data

    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    try:
        lines = conn.execute(
            "SELECT * FROM invoice_lines WHERE invoice_id = ? ORDER BY line_number",
            (invoice_id,)).fetchall()
    finally:
        conn.close()
    assert [line["description"] for line in lines] == [
        "Wireless Keyboard PRO", "Laptop Stand", "New Gadget"]
    assert [line["line_number"] for line in lines] == [1, 2, 3]
    assert lines[0]["quantity"] == 3.0 and lines[0]["amount"] == 300.0
    assert lines[2]["quantity"] == 2.0 and lines[2]["amount"] == 602.0


def test_blank_rows_ignored_on_save(app, client, make_pdf):
    """TC-S3-I07 — leaving the blank add-rows empty stores no extra lines."""
    _upload(client, make_pdf)
    invoice_id = _last_id(app)
    _save(client, invoice_id, _save_form())
    conn = sqlite3.connect(app.config["DATABASE"])
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM invoice_lines WHERE invoice_id = ?",
            (invoice_id,)).fetchone()[0]
    finally:
        conn.close()
    assert count == 0  # synthetic invoice has no table; blank rows ignored


# ------------------------------------------------- validation (US-S3-04)

def test_invalid_submission_persists_nothing(app, client, make_pdf):
    """TC-S3-I08 — blocked validation: status stays extracted, no lines,
    per-field errors rendered."""
    _upload(client, make_pdf)
    invoice_id = _last_id(app)
    response = client.post(
        f"/invoices/{invoice_id}/save",
        data=_save_form(invoice_number="", invoice_date="15/01/2026",
                        subtotal="abc"),
        follow_redirects=True,
    )
    assert b"could not be saved" in response.data
    assert b"Invoice number is required" in response.data
    assert b"YYYY-MM-DD" in response.data
    assert b"must be a number" in response.data
    row = _rows(app, f"SELECT * FROM invoices WHERE id = {invoice_id}")[0]
    assert row["status"] == "extracted"  # nothing persisted
    assert row["invoice_number"] == "INV-TEST-0001"  # original values intact


def test_consistency_mismatch_warns_but_saves(app, client, make_pdf):
    """TC-S3-I09 — totals mismatch: visible warning, save allowed (E-16)."""
    _upload(client, make_pdf)
    invoice_id = _last_id(app)
    response = _save(client, invoice_id, _save_form(total="9999.99"))
    assert b"does not match the total" in response.data
    row = _rows(app, f"SELECT * FROM invoices WHERE id = {invoice_id}")[0]
    assert row["status"] == "saved" and row["total"] == 9999.99


def test_decimal_quantization_on_save(app, client, make_pdf):
    """TC-S3-I10 — '1080.5' is stored as 1080.5 (== 1080.50 quantized)."""
    _upload(client, make_pdf)
    invoice_id = _last_id(app)
    _save(client, invoice_id, _save_form(total="1080.5"))
    row = _rows(app, f"SELECT * FROM invoices WHERE id = {invoice_id}")[0]
    assert row["total"] == 1080.5


# ------------------------------------------------- atomic save (US-S3-05)

def test_rollback_on_injected_repository_failure(app, monkeypatch):
    """TC-S3-I11 — mid-transaction failure rolls back header AND lines.

    Injection point: the repository's Decimal→REAL boundary raises for one
    poisoned line amount — i.e. after the header UPDATE and line DELETE have
    run inside the transaction. Rollback must undo all of it.
    """
    import app.db.repository as repository

    invoice_id = _extract_real_001(app)
    before_header = _rows(app, f"SELECT * FROM invoices WHERE id = {invoice_id}")[0]
    before_lines = _rows(
        app,
        f"SELECT * FROM invoice_lines WHERE invoice_id = {invoice_id} ORDER BY line_number",
    )
    assert before_header["status"] == "extracted" and len(before_lines) == 3

    poison = object()  # sentinel no legitimate value can equal
    real_to_real = repository._to_real

    def failing_to_real(value):
        if value is poison:
            raise RuntimeError("injected repository failure")
        return real_to_real(value)

    with app.app_context():
        header = {
            "vendor": "Changed Vendor", "vendor_tax_id": None,
            "invoice_number": "CHANGED", "invoice_date": "2026-10-06",
            "due_date": None, "bill_to": None, "currency": "INR",
            "subtotal": Decimal("1.00"), "discount": None, "tax": None,
            "tax_rate": None, "total": Decimal("1.00"),
        }
        lines = [{"line_number": 1, "description": "X", "quantity": Decimal("1"),
                  "unit_price": Decimal("1"), "amount": poison}]
        monkeypatch.setattr(repository, "_to_real", failing_to_real)
        conn = repository.sqlite3.connect(app.config["DATABASE"])
        conn.row_factory = sqlite3.Row  # get_db sets this in production
        try:
            with pytest.raises(RuntimeError):
                repository.save_invoice(conn, invoice_id, header=header, lines=lines)
        finally:
            conn.close()

    # nothing changed: status, header values, and the original 3 lines remain
    after_header = _rows(app, f"SELECT * FROM invoices WHERE id = {invoice_id}")[0]
    after_lines = _rows(
        app,
        f"SELECT * FROM invoice_lines WHERE invoice_id = {invoice_id} ORDER BY line_number",
    )
    assert after_header["status"] == "extracted"
    assert after_header["vendor"] == "TechNova Retail Pvt. Ltd."
    assert after_header["invoice_number"] == "TN-2026-1001"
    assert len(after_lines) == 3
    assert [line["description"] for line in after_lines] == [
        line["description"] for line in before_lines
    ]


def test_double_submit_guard(app, client, make_pdf):
    """TC-S3-I12 — saving an already-saved record is rejected, not duplicated."""
    _upload(client, make_pdf)
    invoice_id = _last_id(app)
    _save(client, invoice_id, _save_form())
    response = client.post(f"/invoices/{invoice_id}/save",
                           data=_save_form(), follow_redirects=True)
    assert b"cannot be saved again" in response.data
    assert len(_rows(app, "SELECT * FROM invoices WHERE status='saved'")) == 1


def test_extraction_json_unchanged_by_save(app, client, make_pdf):
    """TC-S3-I13 — extraction_json is the untouched pre-review audit record."""
    _upload(client, make_pdf)
    invoice_id = _last_id(app)
    before = _rows(app, f"SELECT extraction_json FROM invoices WHERE id = {invoice_id}")[0][0]
    _save(client, invoice_id, _save_form(vendor="Edited Vendor"))
    after = _rows(app, f"SELECT extraction_json FROM invoices WHERE id = {invoice_id}")[0][0]
    assert before == after
    assert json.loads(after)["fields"]["vendor"]["value"] == "Acme Corporation"


# ------------------------------------------------- duplicates (US-S3-06)

def test_duplicate_requires_confirmation(app, client, make_pdf):
    """TC-S3-I14 — same vendor+number: warning, no record until confirmed."""
    _upload(client, make_pdf, name="a.pdf")
    first_id = _last_id(app)
    _save(client, first_id, _save_form())
    _upload(client, make_pdf, name="b.pdf")        # same content → same vendor+number
    second_id = _last_id(app)
    assert second_id != first_id

    blocked = _save(client, second_id, _save_form())
    assert b"Possible duplicate" in blocked.data
    assert b"Save anyway" in blocked.data
    saved_count = len(_rows(app, "SELECT * FROM invoices WHERE status='saved'"))
    assert saved_count == 1  # nothing new created

    confirmed = client.post(
        f"/invoices/{second_id}/save",
        data={**_save_form(), "confirm_duplicate": "1"},
        follow_redirects=True,
    )
    assert b"Invoice #" in confirmed.data
    assert len(_rows(app, "SELECT * FROM invoices WHERE status='saved'")) == 2


def test_duplicate_vendor_number_only_not_hash(app, client, make_pdf):
    """TC-S3-I15 — different file, same vendor+number → still a duplicate."""
    variant = list(SYNTHETIC)
    variant[2] = "1 Main Street, Springfield Invoice Date: 2026-02-20"
    _upload(client, make_pdf, name="a.pdf", text_lines=SYNTHETIC)
    _save(client, _last_id(app), _save_form())
    _upload(client, make_pdf, name="b.pdf", text_lines=variant)
    second_id = _last_id(app)
    blocked = _save(client, second_id, _save_form(invoice_date="2026-02-20"))
    assert b"Possible duplicate" in blocked.data


def test_different_invoice_not_flagged(app, client, make_pdf):
    """TC-S3-I16 — different vendor+number saves with no duplicate warning."""
    _upload(client, make_pdf, name="a.pdf", text_lines=SYNTHETIC)
    _save(client, _last_id(app), _save_form())
    variant = list(SYNTHETIC)
    variant[1] = "Acme Corporation Invoice No: INV-TEST-0002"
    _upload(client, make_pdf, name="b.pdf", text_lines=variant)
    second_id = _last_id(app)
    response = _save(client, second_id,
                     _save_form(invoice_number="INV-TEST-0002"))
    assert b"Possible duplicate" not in response.data
    assert b"Invoice #" in response.data


# ------------------------------------------------- success & security

def test_success_flash_and_status(app, client, make_pdf):
    """TC-S3-I17 — success message shown; record listed as saved (US-S3-07)."""
    _upload(client, make_pdf)
    invoice_id = _last_id(app)
    response = _save(client, invoice_id, _save_form())
    assert f"Invoice #{invoice_id} saved.".encode() in response.data
    assert b"saved" in response.data  # status badge on home page


def test_origin_check_blocks_cross_site_post(app, client, make_pdf):
    """TC-S3-I18 — POST with a foreign Origin is rejected with 403 (T-G)."""
    _upload(client, make_pdf)
    invoice_id = _last_id(app)
    response = client.post(
        f"/invoices/{invoice_id}/save",
        data=_save_form(),
        headers={"Origin": "http://evil.example"},
    )
    assert response.status_code == 403
    # same-origin POST is fine:
    ok = client.post(
        f"/invoices/{invoice_id}/save",
        data=_save_form(),
        headers={"Origin": "http://127.0.0.1:5000"},
        follow_redirects=True,
    )
    assert b"Invoice #" in ok.data


def test_service_level_duplicate_finder(app):
    """TC-S3-I19 — find_saved_duplicates matches case-insensitively, saved only."""
    with app.app_context():
        conn = get_db()
        from app.db.repository import find_saved_duplicates, insert_invoice
        saved = insert_invoice(conn, file_hash="h1", original_filename="o",
                               stored_filename="s", status="saved")
        insert_invoice(conn, file_hash="h2", original_filename="o2",
                       stored_filename="s2", status="extracted")
        conn.execute(
            "UPDATE invoices SET vendor = 'Acme Corp', invoice_number = 'INV-1' "
            "WHERE id = ?", (saved,))
        conn.commit()
        # case-insensitive vendor + number match; drafts never count
        dupes = find_saved_duplicates(conn, "acme corp", "inv-1")
        drafts = find_saved_duplicates(conn, "nothing", "nowhere")
        conn.close()
    assert len(dupes) == 1 and dupes[0]["id"] == saved
    assert drafts == []


def test_validate_service_smoke_on_real_draft(app):
    """TC-S3-I20 — review validation accepts the real invoice's values."""
    sample = SAMPLES / "invoice_001_retail.pdf"
    if not sample.exists():
        pytest.skip("sample not present")
    with app.app_context():
        record = store_upload(FileStorage(io.BytesIO(sample.read_bytes()),
                                          filename=sample.name,
                                          content_type="application/pdf"))
        extract_invoice(record["id"])
    form = {
        "vendor": "TechNova Retail Pvt. Ltd.", "vendor_tax_id": "29AABCT1234F1Z5",
        "invoice_number": "TN-2026-1001", "invoice_date": "2026-10-06",
        "due_date": "", "bill_to": "Gagan K M, Bengaluru, Karnataka",
        "currency": "INR", "subtotal": "6550.00", "discount": "0.00",
        "tax": "1179.00", "tax_rate": "18", "total": "7729.00",
    }
    result = validate_and_merge(form)
    assert result["ok"] is True and result["warnings"] == []
    assert len(result["data"]["lines"]) == 0  # no line rows submitted
