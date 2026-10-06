"""Sprint 2 unit tests — field strategies on synthetic text fixtures.
IDs TC-S2-F01… (catalogued in docs/04). Fixtures are plain text/tables —
the parser contract is text-in/draft-out, no PDFs needed.
"""
from decimal import Decimal

from app.services.parser.fields import build_fields

SAMPLE_TABLE = [
    [
        "TechNova Retail Pvt. Ltd.\n42 MG Road, Bengaluru, Karnataka 560001"
        "\nGSTIN: 29AABCT1234F1Z5",
        "Invoice No: TN-2026-1001\nInvoice Date: 06-Oct-2026\nPayment: Due on receipt",
    ],
    ["Bill To:\nGagan K M\nBengaluru, Karnataka", None],
]

# parse() takes a LIST of tables (pdfplumber's shape).
SAMPLE_TABLES = [SAMPLE_TABLE]


def _fields(text, tables=None):
    return build_fields(text, tables if tables is not None else [])


REALISTIC_TEXT = """TAX INVOICE
TechNova Retail Pvt. Ltd. Invoice No: TN-2026-1001
42 MG Road, Bengaluru, Karnataka 560001 Invoice Date: 06-Oct-2026
GSTIN: 29AABCT1234F1Z5 Payment: Due on receipt
Bill To:
Gagan K M
Bengaluru, Karnataka
# Description Qty Unit Price Amount
1 Wireless Keyboard 2 n1,250.00 n2,500.00
Subtotal n6,550.00
Discount n0.00
GST (18%) n1,179.00
Grand Total n7,729.00"""


def test_invoice_number_midline_label():
    """TC-S2-F01 — 'Invoice No:' mid-line after the vendor name (finding 6)."""
    fields = _fields(REALISTIC_TEXT, SAMPLE_TABLES)
    assert fields["invoice_number"]["status"] == "found"
    assert fields["invoice_number"]["value"] == "TN-2026-1001"


def test_invoice_date_real_format():
    """TC-S2-F02 — 'Invoice Date: 06-Oct-2026' → ISO found."""
    fields = _fields(REALISTIC_TEXT, SAMPLE_TABLES)
    assert fields["invoice_date"] == {"status": "found", "value": "2026-10-06"}


def test_due_date_found_when_present():
    """TC-S2-F03 — a real due date parses."""
    text = "INVOICE\nDue Date: 2026-02-01\nTotal $10.00"
    assert _fields(text)["due_date"]["value"] == "2026-02-01"


def test_due_receipt_never_a_date():
    """TC-S2-F04 — 'Payment: Due on receipt' must not become a due date."""
    fields = _fields(REALISTIC_TEXT, SAMPLE_TABLES)
    assert fields["due_date"]["status"] == "missing"


def test_bill_to_multiline_until_table():
    """TC-S2-F05 — bill-to collects lines, stops at the item header."""
    fields = _fields(REALISTIC_TEXT, SAMPLE_TABLES)
    assert fields["bill_to"]["value"] == "Gagan K M, Bengaluru, Karnataka"


def test_vendor_from_table_cell_with_address_and_taxid():
    """TC-S2-F06 — vendor/address/tax-id from the multi-line table cell."""
    fields = _fields(REALISTIC_TEXT, SAMPLE_TABLES)
    assert fields["vendor"]["value"] == "TechNova Retail Pvt. Ltd."
    assert fields["vendor_tax_id"]["value"] == "29AABCT1234F1Z5"


def test_tax_rate_and_amount_separate():
    """TC-S2-F07 — 'GST (18%) n1,179.00': rate 18, amount 1179 (regression)."""
    fields = _fields(REALISTIC_TEXT, SAMPLE_TABLES)
    assert fields["tax_rate"]["value"] == 18.0
    assert fields["tax"]["value"] == Decimal("1179.00")


def test_gstin_line_is_not_tax_amount():
    """TC-S2-F11 — 'GSTIN: 29AABCT1234F1Z5' must not match the gst label."""
    fields = _fields(REALISTIC_TEXT, SAMPLE_TABLES)
    assert fields["tax"]["value"] == Decimal("1179.00")
    assert fields["tax"]["value"] != Decimal("29123415.00")


def test_grand_total_preferred_over_subtotal():
    """TC-S2-F08 — 'Subtotal/Total/Grand Total' on one page picks Grand Total."""
    text = """INVOICE
Subtotal $1,000.00
Tax $80.00
Total $1,080.00
Grand Total $1,080.00"""
    fields = _fields(text)
    assert fields["total"]["value"] == Decimal("1080.00")


def test_total_does_not_match_inside_subtotal():
    """TC-S2-F09 — 'Subtotal' never satisfies the generic 'total' label."""
    text = "INVOICE\nSubtotal $5.00"
    fields = _fields(text)
    assert fields["subtotal"]["value"] == Decimal("5.00")
    assert fields["total"]["status"] == "missing"


def test_zero_discount_is_found():
    """TC-S2-F10 — 'Discount n0.00' is a found zero, not missing (E-10 nuance)."""
    fields = _fields(REALISTIC_TEXT, SAMPLE_TABLES)
    assert fields["discount"]["status"] == "found"
    assert fields["discount"]["value"] == Decimal("0.00")


def test_missing_labels_yield_missing_fields():
    """TC-S2-F12 — unrelated text: every field missing, nothing invented."""
    fields = _fields("The quick brown fox jumps over the lazy dog.")
    for name in (
        "vendor", "vendor_tax_id", "invoice_number", "invoice_date",
        "due_date", "bill_to", "currency", "subtotal", "discount",
        "tax_rate", "tax", "total",
    ):
        assert fields[name]["status"] == "missing", name


def test_currency_inr_flagged_from_gst_context():
    """TC-S2-F13 — 'n' glyph + GSTIN: INR, ambiguous, evidence kept."""
    fields = _fields(REALISTIC_TEXT, SAMPLE_TABLES)
    assert fields["currency"]["status"] == "ambiguous"
    assert fields["currency"]["value"] == "INR"
    assert "GSTIN" in fields["currency"]["evidence"]


def test_vendor_geometric_fallback_without_tables():
    """TC-S2-F14 — no tables: vendor falls back to first non-title line."""
    text = "TAX INVOICE\nAcme Corporation\n1 Main Street\nTotal $5.00"
    fields = _fields(text, tables=[])
    assert fields["vendor"]["value"] == "Acme Corporation"
