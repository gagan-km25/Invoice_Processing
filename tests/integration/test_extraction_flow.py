"""Sprint 2 integration tests — extraction flow over HTTP and the five real
sample invoices with EXACT expected values (transcribed from the Phase-A
exploration in docs/07, before any parser code existed).

Real-invoice cases (TC-S2-E01…E05) skip when sample_invoices/ lacks the file —
samples are git-ignored by design, so a fresh clone runs the rest of the suite.
"""
import io
import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from werkzeug.datastructures import FileStorage

from app.services.extraction import extract_invoice
from app.services.uploading import store_upload

SAMPLES = Path(__file__).resolve().parents[2] / "sample_invoices"

SYNTHETIC_INVOICE = [
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


# ------------------------------------------------------------------ HTTP flow

def test_upload_runs_extraction_and_persists(app, client, make_pdf):
    """TC-S2-I01 — upload → extracted: columns, lines, draft JSON, flash."""
    _, pdf_bytes = make_pdf("synthetic.pdf", pages=1, text_lines=SYNTHETIC_INVOICE)
    response = client.post(
        "/upload",
        data={"file": (io.BytesIO(pdf_bytes), "synthetic.pdf")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Extraction complete" in response.data
    assert b"extracted" in response.data  # status badge

    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM invoices").fetchone()
        lines = conn.execute(
            "SELECT * FROM invoice_lines ORDER BY line_number"
        ).fetchall()
    finally:
        conn.close()
    assert row["status"] == "extracted"
    assert row["invoice_number"] == "INV-TEST-0001"
    assert row["invoice_date"] == "2026-01-15"
    assert row["vendor"] == "Acme Corporation"
    assert row["currency"] == "USD"
    assert row["subtotal"] == 1000.00
    assert row["tax"] == 80.00
    assert row["total"] == 1080.00
    assert row["extraction_json"]  # draft persisted (resumable review, S3)
    draft = json.loads(row["extraction_json"])
    assert draft["meta"]["parser_version"] >= 1
    assert lines == []  # synthetic invoice has no item table → zero lines (AC-2.3)


def test_extraction_failure_marks_record_failed(app, client, make_pdf):
    """TC-S2-I02 — a valid PDF whose extraction explodes → failed + reason."""
    # A valid PDF (opens fine) that makes the parser raise is hard to craft;
    # instead verify the service-level failure path with a vanished file:
    _, pdf_bytes = make_pdf("ghost.pdf", pages=1)
    with app.app_context():
        record = store_upload(
            FileStorage(io.BytesIO(pdf_bytes), filename="ghost.pdf")
        )
        (app.config["UPLOAD_DIR"] / record["stored_filename"]).unlink()
        ok, message = extract_invoice(record["id"],)

        assert ok is False
        assert "could not be read" in message
        conn = sqlite3.connect(app.config["DATABASE"])
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT status, error_message FROM invoices").fetchone()
        finally:
            conn.close()
        assert row["status"] == "failed"
        assert "could not be read" in row["error_message"]


# ------------------------------------------------- the five real invoices
# Expected values transcribed from docs/07 Phase A (raw pdfplumber inspection
# BEFORE parser code) — exact-value assertions, never just non-empty (Phase D).

def _expected(**overrides):
    base = {
        "status": "extracted",
        "due_date": None,
        "currency": "INR",
        "currency_status": "ambiguous",
        "checks_pass": True,
    }
    base.update(overrides)
    return base


REAL_CASES = [
    pytest.param(
        "invoice_001_retail.pdf",
        _expected(
            vendor="TechNova Retail Pvt. Ltd.",
            address="42 MG Road, Bengaluru, Karnataka 560001",
            tax_id="29AABCT1234F1Z5",
            number="TN-2026-1001",
            date="2026-10-06",
            bill_to="Gagan K M, Bengaluru, Karnataka",
            subtotal="6550.00", discount="0.00", rate=18.0,
            tax="1179.00", total="7729.00",
            lines=[
                (1, "Wireless Keyboard", "2", "1250.00", "2500.00"),
                (2, "USB-C Hub", "1", "1850.00", "1850.00"),
                (3, "Laptop Stand", "1", "2200.00", "2200.00"),
            ],
        ),
        id="TC-S2-E01-retail",
    ),
    pytest.param(
        "invoice_002_services.pdf",
        _expected(
            vendor="BrightEdge Consulting",
            address="18 Residency Road, Bengaluru, Karnataka 560025",
            tax_id="29AAFCB5678G1Z2",
            number="BEC-SVC-2617",
            date="2026-10-05",
            bill_to="Nagarjuna College of Engineering, Bengaluru, Karnataka",
            subtotal="31500.00", discount="500.00", rate=18.0,
            tax="5580.00", total="36580.00",
            lines=[
                (1, "Software Consulting", "10", "1800.00", "18000.00"),
                (2, "Technical Documentation", "5", "1200.00", "6000.00"),
                (3, "System Review", "3", "2500.00", "7500.00"),
            ],
        ),
        id="TC-S2-E02-services",
    ),
    pytest.param(
        "invoice_003_multiitem.pdf",
        _expected(
            vendor="Metro Office Supplies",
            address="77 Commercial Street, Bengaluru, Karnataka 560001",
            tax_id="29AAMO7890H1Z7",
            number="MOS-88421",
            date="2026-10-04",
            bill_to="Apex Solutions India Pvt. Ltd., Bengaluru, Karnataka",
            subtotal="14045.00", discount="750.00", rate=12.0,
            tax="1595.40", total="14890.40",
            lines=[
                (1, "A4 Copier Paper", "10", "320.00", "3200.00"),
                (2, "Ball Pens - Box", "5", "180.00", "900.00"),
                (3, "Stapler", "4", "260.00", "1040.00"),
                (4, "File Folders", "20", "45.00", "900.00"),
                (5, "Desk Organizer", "3", "375.00", "1125.00"),
                (6, "Printer Toner", "2", "2450.00", "4900.00"),
                (7, "Notebooks", "12", "95.00", "1140.00"),
                (8, "Markers Pack", "4", "210.00", "840.00"),
            ],
        ),
        id="TC-S2-E03-multiitem",
    ),
    pytest.param(
        "invoice_004_alternate.pdf",
        _expected(
            vendor="GreenLeaf Foods & Beverages",
            address="12 Indiranagar 100 Feet Road, Bengaluru 560038",
            tax_id="29AAGFG4567J1Z9",
            number="GLF/26/4078",
            date="2026-10-03",
            bill_to="Cityview Hotel, Bengaluru, Karnataka",
            subtotal="15600.00", discount="300.00", rate=5.0,
            tax="765.00", total="16065.00",
            lines=[
                (1, "Premium Coffee Beans", "8", "850.00", "6800.00"),
                (2, "Tea Assortment", "10", "420.00", "4200.00"),
                (3, "Sugar Sachets", "20", "110.00", "2200.00"),
                (4, "Paper Cups", "15", "160.00", "2400.00"),
            ],
        ),
        id="TC-S2-E04-alternate",
    ),
    pytest.param(
        "invoice_005_complex.pdf",
        _expected(
            vendor="CloudPeak Systems India Pvt. Ltd.",
            address="5 Outer Ring Road, Marathahalli, Bengaluru 560037",
            tax_id="29AACC9012K1Z4",
            number="CPS-INV-2026-552",
            date="2026-10-01",
            bill_to="Vertex Digital Labs, Bengaluru, Karnataka",
            subtotal="52100.00", discount="1250.00", rate=18.0,
            tax="9153.00", total="60003.00",
            lines=[
                (1, "Cloud Hosting - Basic", "1", "18500.00", "18500.00"),
                (2, "Database Service", "2", "7200.00", "14400.00"),
                (3, "Backup Storage", "3", "3100.00", "9300.00"),
                (4, "Monitoring Add-on", "1", "4500.00", "4500.00"),
                (5, "Technical Support", "6", "900.00", "5400.00"),
            ],
        ),
        id="TC-S2-E05-complex",
    ),
]


def _assert_exact(app, sample_name, expected):
    sample = SAMPLES / sample_name
    if not sample.exists():
        pytest.skip(f"sample not present: {sample_name}")
    with app.app_context():
        record = store_upload(_storage(sample))
        ok, message = extract_invoice(record["id"],)
        assert ok is True, message

        conn = sqlite3.connect(app.config["DATABASE"])
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM invoices WHERE id = ?", (record["id"],)
            ).fetchone()
            db_lines = conn.execute(
                "SELECT * FROM invoice_lines WHERE invoice_id = ? ORDER BY line_number",
                (record["id"],),
            ).fetchall()
        finally:
            conn.close()
        draft = json.loads(row["extraction_json"])
        fields = draft["fields"]

        # exact header expectations
        assert row["status"] == expected["status"]
        assert row["vendor"] == expected["vendor"]
        assert draft["vendor_address"] == expected["address"]
        assert row["vendor_tax_id"] == expected["tax_id"]
        assert row["invoice_number"] == expected["number"]
        assert row["invoice_date"] == expected["date"]
        assert row["due_date"] is None and fields["due_date"]["status"] == "missing"
        assert row["bill_to"] == expected["bill_to"]
        assert row["currency"] == expected["currency"]
        assert fields["currency"]["status"] == expected["currency_status"]
        for column, key in (
            ("subtotal", "subtotal"), ("discount", "discount"),
            ("tax", "tax"), ("total", "total"),
        ):
            assert row[column] == float(expected[key]), (column, row[column])
            assert Decimal(fields[key]["value"]) == Decimal(expected[key])  # JSON draft stores Decimals as strings
        assert row["tax_rate"] == expected["rate"]
        assert row["page_count"] == 1

        # exact line items, cell for cell
        assert len(db_lines) == len(expected["lines"])
        for db_line, (no, desc, qty, unit, amount) in zip(db_lines, expected["lines"]):
            assert db_line["line_number"] == no
            assert db_line["description"] == desc
            assert db_line["quantity"] == float(qty)
            assert db_line["unit_price"] == float(unit)
            assert db_line["amount"] == float(amount)

        # consistency checks all pass on real invoices
        assert expected["checks_pass"] and all(
            check["passed"] for check in draft["checks"]
        )


def _storage(path: Path):
    from werkzeug.datastructures import FileStorage

    return FileStorage(
        stream=io.BytesIO(path.read_bytes()),
        filename=path.name,
        content_type="application/pdf",
    )


@pytest.mark.parametrize("sample_name,expected", REAL_CASES)
def test_real_invoice_exact(app, sample_name, expected):
    _assert_exact(app, sample_name, expected)
