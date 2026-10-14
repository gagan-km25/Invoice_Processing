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


# ------------------------------------------------- Sprint E6 parser fixes
# Regression evidence for the two defects found during the isolated UI
# session (CPS-INV-5099): missing explicit-currency-label support, and the
# items-table header cell extracted as the vendor.

CPS_TEXT = """CloudPeak Systems
Bengaluru, Karnataka
INVOICE
Invoice Number: CPS-INV-5099
Invoice Date: 2026-10-05
Due Date: 2026-10-25
GSTIN: 29WXYZA7890B1Z6
Currency: INR
Description Qty Unit Price Amount
Cloud Server Subscription 3 INR 4,500.00 INR 13,500.00
Database Hosting 2 INR 3,200.00 INR 6,400.00
Backup Storage 5 INR 900.00 INR 4,500.00
Security Monitoring 1 INR 2,800.00 INR 2,800.00
Technical Support 4 INR 1,250.00 INR 5,000.00
Subtotal INR 32,200.00
Discount INR 1,250.00
GST (18%) INR 5,571.00
Total INR 36,521.00"""

# pdfplumber's single table for that layout: the item table, whose first
# cell is the header word "Description".
CPS_TABLES = [[["Description", "Qty", "Unit Price", "Amount"],
               ["Cloud Server Subscription", "3", "INR 4,500.00",
                "INR 13,500.00"]]]


def test_currency_label_found_with_plain_number_amounts():
    """TC-E6-F01 — 'Currency: INR' is honored even when every amount is a
    plain number without a glyph (verified defect on CPS-INV-5099)."""
    fields = build_fields(CPS_TEXT, CPS_TABLES)
    assert fields["currency"] == {"status": "found", "value": "INR",
                                  "raw": "INR"}


def test_currency_label_beats_symbol_inference():
    """TC-E6-F02 — an explicit labeled code wins over glyph/GST inference
    (deterministic precedence: label > symbol > context inference)."""
    text = REALISTIC_TEXT + "\nCurrency: EUR"
    fields = build_fields(text, [])
    assert fields["currency"]["status"] == "found"
    assert fields["currency"]["value"] == "EUR"


def test_currency_label_invalid_value_is_ambiguous():
    """TC-E6-F03 — a label whose value is not a 3-letter code never becomes
    a guessed 'found': ambiguous with evidence, value None."""
    text = REALISTIC_TEXT + "\nCurrency: dollars"
    fields = build_fields(text, [])
    assert fields["currency"]["status"] == "ambiguous"
    assert fields["currency"]["value"] is None
    assert "3-letter" in fields["currency"]["evidence"]


def test_currency_without_label_or_glyph_stays_missing():
    """TC-E6-F04 — plain-number amounts with no label/glyph keep the
    documented pre-fix missing behavior (no guessed currency)."""
    text = """INVOICE
Acme Ltd Invoice No: A-1
Invoice Date: 2026-01-02
Subtotal 100.00
Tax 8.00
Total 108.00"""
    fields = build_fields(text, [])
    assert fields["currency"]["status"] == "missing"
    assert fields["currency"]["value"] is None


def test_symbol_amounts_still_resolve_without_label():
    """TC-E6-F05 — pre-existing behavior preserved: '$' amounts resolve via
    the symbol table when no label is present."""
    text = """INVOICE
Acme Ltd Invoice No: A-1
Invoice Date: 2026-01-02
Subtotal $100.00
Tax $8.00
Total $108.00"""
    fields = build_fields(text, [])
    assert fields["currency"] == {"status": "found", "value": "USD"}


def test_items_table_header_cell_is_not_the_vendor():
    """TC-E6-F06 — a layout whose first (only) table is the item table must
    not yield 'Description' as the vendor; the geometric fallback finds the
    real vendor line and flags it ambiguous (verified defect)."""
    fields = build_fields(CPS_TEXT, CPS_TABLES)
    assert fields["vendor"]["value"] == "CloudPeak Systems"
    assert fields["vendor"]["status"] == "ambiguous"


def test_vendor_table_after_items_table_still_found():
    """TC-E6-F07 — when the items table comes first and a later table
    carries the vendor cell, the guard skips the header cell and the real
    vendor block is found."""
    tables = [[["Description", "Qty", "Unit Price", "Amount"],
               ["Item", "1", "5.00", "5.00"]],
              SAMPLE_TABLE]
    fields = build_fields(REALISTIC_TEXT, tables)
    assert fields["vendor"]["status"] == "found"
    assert fields["vendor"]["value"] == "TechNova Retail Pvt. Ltd."
