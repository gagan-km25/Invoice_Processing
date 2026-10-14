"""Sprint E3 acceptance-evidence tests — US-E3-3 extended fields end-to-end.

Direct coverage for the gap identified in the E3 acceptance review:
pipeline persistence of the extended §6 columns (po_number, bill-to/ship-to,
GSTIN, per-line tax), review-form prefill, save persistence, reload
round-trip. Isolated tmp databases via the shared fixtures only; extraction
is stubbed so drafts are deterministic (same pattern as test_e3_validation).
"""
import io
import sqlite3

from app.db import get_db
from app.services import extraction


def _field(value):
    return {"status": "found", "value": value}


def _extended_draft(**overrides):
    """A valid draft that also carries every §6 extended field."""
    fields = {
        "invoice_number": _field("INV-XF-0001"),
        "invoice_date": _field("2026-09-30"),
        "vendor": _field("Acme Corporation"),
        "currency": _field("USD"),
        "subtotal": _field("100.00"),
        "tax": _field("8.00"),
        "total": _field("108.00"),
        "vendor_tax_id": _field("29AABCT1234F1Z5"),
        "bill_to": _field("Gagan K M"),
        "bill_to_address": _field("42 MG Road, Bengaluru"),
        "ship_to_name": _field("Acme Warehouse"),
        "ship_to_address": _field("7 Industrial Area, Bengaluru"),
        "po_number": _field("PO-2026-77"),
    }
    fields.update(overrides)
    return {
        "fields": fields,
        "lines": [{"line_number": 1, "description": "Widget",
                   "quantity": "2", "unit_price": "50.00",
                   "amount": "100.00", "tax": "2.50"}],
        "checks": [],
        "meta": {"page_count": 1, "parser_version": 1, "source": "stub"},
    }


def _stub_extraction(monkeypatch, draft):
    def fake(invoice_id):
        conn = get_db()
        try:
            from app.db.repository import update_extraction

            update_extraction(conn, invoice_id, draft=draft, write_lines=True)
        finally:
            conn.close()
        return True, "stubbed extraction"

    monkeypatch.setattr(extraction, "extract_stored_invoice", fake)


def _upload(client, pdf_storage, name="xf.pdf"):
    storage = pdf_storage(name)
    return client.post(
        "/upload",
        data={"file": (io.BytesIO(storage.read()), name)},
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def _row(app, invoice_id):
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "SELECT * FROM invoices WHERE id = ?", (invoice_id,)
        ).fetchone()
    finally:
        conn.close()


def _lines(app, invoice_id):
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "SELECT * FROM invoice_lines WHERE invoice_id = ? "
            "ORDER BY line_number", (invoice_id,)
        ).fetchall()
    finally:
        conn.close()


# ------------------------------------------- 1. extraction → column mapping

def test_pipeline_persists_extended_fields(
    app, client, worker, pdf_storage, monkeypatch
):
    """TC-E3-XF-I01 — update_extraction maps every §6 draft field into its
    column and the per-line tax into invoice_lines.line_tax."""
    _stub_extraction(monkeypatch, _extended_draft())
    _upload(client, pdf_storage)
    assert worker.run_pending() == 1

    row = _row(app, 1)
    assert row["status"] == "completed"
    assert row["po_number"] == "PO-2026-77"
    assert row["bill_to_address"] == "42 MG Road, Bengaluru"
    assert row["ship_to_name"] == "Acme Warehouse"
    assert row["ship_to_address"] == "7 Industrial Area, Bengaluru"
    assert row["vendor_tax_id"] == "29AABCT1234F1Z5"
    assert row["bill_to"] == "Gagan K M"
    lines = _lines(app, 1)
    assert len(lines) == 1
    assert lines[0]["line_tax"] == 2.50


def test_pipeline_handles_absent_extended_fields(
    app, client, worker, pdf_storage, monkeypatch
):
    """TC-E3-XF-I02 — a draft without extended fields leaves the columns
    NULL (no fabricated values, no crash)."""
    minimal = _extended_draft()
    for name in ("po_number", "bill_to_address", "ship_to_name",
                 "ship_to_address", "vendor_tax_id"):
        minimal["fields"].pop(name)
    minimal["fields"]["bill_to"] = _field("Plain Buyer")
    minimal["lines"][0]["tax"] = None
    _stub_extraction(monkeypatch, minimal)
    _upload(client, pdf_storage)
    assert worker.run_pending() == 1

    row = _row(app, 1)
    for name in ("po_number", "bill_to_address", "ship_to_name",
                 "ship_to_address", "vendor_tax_id"):
        assert row[name] is None, name
    assert row["bill_to"] == "Plain Buyer"
    assert _lines(app, 1)[0]["line_tax"] is None


# --------------------------------------------------- 2. review-form prefill

def test_review_page_prefills_extended_fields(
    app, client, worker, pdf_storage, monkeypatch
):
    """TC-E3-XF-I03 — GET review renders the extended values into the form
    inputs, including the per-line tax input."""
    _stub_extraction(monkeypatch, _extended_draft())
    _upload(client, pdf_storage)
    assert worker.run_pending() == 1

    html = client.get("/invoices/1/review").data.decode()
    assert 'name="po_number"' in html and 'value="PO-2026-77"' in html
    assert 'value="42 MG Road, Bengaluru"' in html
    assert 'value="Acme Warehouse"' in html
    assert 'value="7 Industrial Area, Bengaluru"' in html
    assert 'value="29AABCT1234F1Z5"' in html
    assert 'name="tax_0"' in html and 'value="2.50"' in html


# ------------------------------------------------ 3 + 4. save → reload flow

def test_save_persists_extended_fields_and_round_trips(
    app, client, worker, pdf_storage, monkeypatch
):
    """TC-E3-XF-I04 — saving the review persists the extended header
    fields and line tax; reloading the record returns the same values."""
    _stub_extraction(monkeypatch, _extended_draft())
    _upload(client, pdf_storage)
    assert worker.run_pending() == 1

    response = client.post(
        "/invoices/1/save",
        data={
            "vendor": "Acme Corporation",
            "vendor_tax_id": "29AABCT1234F1Z5",
            "invoice_number": "INV-XF-0001",
            "invoice_date": "2026-09-30",
            "due_date": "",
            "bill_to": "Gagan K M",
            "bill_to_address": "1 Saved Street, Bengaluru",
            "ship_to_name": "Saved Warehouse",
            "ship_to_address": "2 Saved Road, Bengaluru",
            "po_number": "PO-SAVED-42",
            "currency": "USD",
            "subtotal": "100.00",
            "discount": "",
            "tax": "8.00",
            "tax_rate": "8",
            "total": "108.00",
            "description_0": "Widget",
            "quantity_0": "2",
            "unit_price_0": "50",
            "amount_0": "100",
            "tax_0": "4.25",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    row = _row(app, 1)
    assert row["status"] == "completed"  # E5: save keeps the lifecycle status
    assert row["po_number"] == "PO-SAVED-42"
    assert row["bill_to_address"] == "1 Saved Street, Bengaluru"
    assert row["ship_to_name"] == "Saved Warehouse"
    assert row["ship_to_address"] == "2 Saved Road, Bengaluru"
    assert row["vendor_tax_id"] == "29AABCT1234F1Z5"
    lines = _lines(app, 1)
    assert lines[0]["line_tax"] == 4.25

    # reload: detail page shows the saved extended values unchanged
    html = client.get("/invoices/1").data.decode()
    assert "PO-SAVED-42" in html
    assert "Saved Warehouse" in html
    assert "2 Saved Road, Bengaluru" in html
    assert "1 Saved Street, Bengaluru" in html
    assert "29AABCT1234F1Z5" in html

    # (The saved COLUMNS are the reload source asserted here; the draft JSON
    # is intentionally untouched by save — AC-05.4.)


def test_save_rejects_invalid_line_tax(
    app, client, worker, pdf_storage, monkeypatch
):
    """TC-E3-XF-I05 — the save route refuses a non-numeric per-line tax
    (strict §6 validation, AC-04.2 rule) and re-renders with the field
    named; nothing is saved."""
    _stub_extraction(monkeypatch, _extended_draft())
    _upload(client, pdf_storage)
    assert worker.run_pending() == 1

    response = client.post(
        "/invoices/1/save",
        data={
            "vendor": "Acme Corporation",
            "vendor_tax_id": "",
            "invoice_number": "INV-XF-0001",
            "invoice_date": "2026-09-30",
            "due_date": "",
            "bill_to": "",
            "currency": "USD",
            "subtotal": "100.00",
            "discount": "",
            "tax": "8.00",
            "tax_rate": "8",
            "total": "108.00",
            "description_0": "Widget",
            "quantity_0": "2",
            "unit_price_0": "50",
            "amount_0": "100",
            "tax_0": "abc",
        },
    )
    assert response.status_code == 400  # blocked, nothing saved
    assert _row(app, 1)["status"] == "completed"  # unchanged
