"""Sprint 2 unit tests — line-item extraction from tables. IDs TC-S2-L01…"""
from decimal import Decimal

from app.services.parser.fields import build_fields
from app.services.parser.lines import extract_line_items, find_item_table

ITEM_TABLE = [
    ["#", "Description", "Qty", "Unit Price", "Amount"],
    ["1", "Wireless Keyboard", "2", "n1,250.00", "n2,500.00"],
    ["2", "USB-C Hub", "1", "n1,850.00", "n1,850.00"],
    ["Subtotal", "n6,550.00"],
    ["Discount", "n0.00"],
    ["GST (18%)", "n1,179.00"],
    ["Grand Total", "n7,729.00"],
]

VENDOR_TABLE = [["Acme Ltd.\n1 Main Street\nGSTIN: 29AABCT1234F1Z5", "Invoice No: X-1"]]


def test_items_and_summary_rows_separated():
    """TC-S2-L01 — items parsed; totals rows surface as summary, not items."""
    items, summary = extract_line_items([VENDOR_TABLE, ITEM_TABLE])
    assert len(items) == 2
    assert items[0] == {
        "line_number": 1,
        "description": "Wireless Keyboard",
        "quantity": Decimal("2.00"),
        "unit_price": Decimal("1250.00"),
        "amount": Decimal("2500.00"),
    }
    assert ("Subtotal", "n6,550.00") in summary
    assert ("Grand Total", "n7,729.00") in summary
    assert all(item["description"] != "Subtotal" for item in items)


def test_no_table_means_zero_lines_no_error():
    """TC-S2-L02 — AC-2.3: no recognizable table → zero lines, no error."""
    items, summary = extract_line_items([])
    assert items == [] and summary == []
    items, summary = extract_line_items(None)
    assert items == [] and summary == []


def test_malformed_rows_dropped():
    """TC-S2-L03/E-15 — rows failing validation are dropped, not guessed."""
    table = [
        ["#", "Description", "Qty", "Unit Price", "Amount"],
        ["1", "Good Row", "2", "$10.00", "$20.00"],
        ["2", "Bad Row", None, None, None],        # no numbers → dropped
        ["x", "Not a number row", "1", "$1", "$1"],  # non-numeric line no
    ]
    items, _ = extract_line_items([table])
    assert [item["description"] for item in items] == ["Good Row"]


def test_header_variants_recognized():
    """TC-S2-L04 — Quantity/Rate header variant still detected."""
    table = [
        ["#", "Item Description", "Quantity", "Rate", "Amount"],
        ["1", "Consulting", "3", "2,500.00", "7,500.00"],
    ]
    assert find_item_table([table]) is table
    items, _ = extract_line_items([table])
    assert items[0]["description"] == "Consulting"
    assert items[0]["amount"] == Decimal("7500.00")


def test_totals_only_table_yields_no_items():
    """TC-S2-L05 — a headerless totals-only table is not an item table:
    zero items. (Totals reach the header strategies via the text layer.)"""
    table = [["Subtotal", "$5.00"], ["Grand Total", "$5.00"]]
    items, summary = extract_line_items([table])
    assert items == []
    assert summary == []


# ------------------------------------------------- Sprint E6 parser fixes
# Headerless four-column layout (verified defect: CPS-INV-5099 extracted
# zero line items because find_item_table required a header row and
# extract_line_items required an integer-leading 5-cell row).

CPS_TABLE = [
    ["Description", "Qty", "Unit Price", "Amount"],
    ["Cloud Server Subscription", "3", "INR 4,500.00", "INR 13,500.00"],
    ["Database Hosting", "2", "INR 3,200.00", "INR 6,400.00"],
    ["Backup Storage", "5", "INR 900.00", "INR 4,500.00"],
    ["Security Monitoring", "1", "INR 2,800.00", "INR 2,800.00"],
    ["Technical Support", "4", "INR 1,250.00", "INR 5,000.00"],
    ["", "", "Subtotal", "INR 32,200.00"],
    ["", "", "Discount", "INR 1,250.00"],
    ["", "", "GST (18%)", "INR 5,571.00"],
    ["", "", "Total", "INR 36,521.00"],
]

# pdfplumber sometimes yields the same table without the header row.
CPS_TABLE_NO_HEADER = CPS_TABLE[1:]


def test_headered_four_column_name_first_rows_extracted():
    """TC-E6-L01 — the real CPS-INV-5099 shape: the header row IS present
    (so find_item_table matches), but item rows are name-first four-column
    [description, qty, unit price, amount] with no line number. All five
    rows extract with exact values; the header row itself is dropped
    ('Qty' is not an amount)."""
    items, _ = extract_line_items([CPS_TABLE])
    assert len(items) == 5
    assert [item["line_number"] for item in items] == [1, 2, 3, 4, 5]
    assert items[0]["description"] == "Cloud Server Subscription"
    assert items[0]["quantity"] == Decimal("3.00")
    assert items[0]["unit_price"] == Decimal("4500.00")
    assert items[0]["amount"] == Decimal("13500.00")
    assert items[4]["description"] == "Technical Support"
    assert items[4]["amount"] == Decimal("5000.00")


def test_headerless_four_column_items_extracted():
    """TC-E6-L01b — the same layout without a header row extracts through
    the headerless fallback with identical results."""
    items, _ = extract_line_items([CPS_TABLE_NO_HEADER])
    assert len(items) == 5
    assert [item["line_number"] for item in items] == [1, 2, 3, 4, 5]
    assert items[0]["description"] == "Cloud Server Subscription"
    assert items[0]["amount"] == Decimal("13500.00")


def test_headerless_summary_rows_kept_out_of_items():
    """TC-E6-L02 — Subtotal/Discount/GST/Total never become line items."""
    items, _ = extract_line_items([CPS_TABLE])
    for label in ("Subtotal", "Discount", "GST", "Total"):
        assert all(item["description"] != label for item in items)


def test_headerless_totals_row_is_summary_not_item():
    """TC-E6-L03 — a totals row (leading empty cells, label in the third
    cell) is not extracted as an item."""
    table = [["Item A", "1", "5.00", "5.00"],
             ["Item B", "2", "6.00", "12.00"],
             ["", "", "Total", "17.00"]]
    items, _ = extract_line_items([table])
    assert [item["description"] for item in items] == ["Item A", "Item B"]


def test_headerless_malformed_rows_dropped():
    """TC-E6-L04 — rows with unparseable amounts are dropped (E-15), the
    rest extract."""
    table = [["Good One", "1", "5.00", "5.00"],
             ["Bad Row", "2", "oops", "12.00"],
             ["Good Two", "3", "6.00", "18.00"]]
    items, _ = extract_line_items([table])
    assert [item["description"] for item in items] == ["Good One", "Good Two"]


def test_headerless_single_qualifying_row_not_fabricated():
    """TC-E6-L05 — fewer than two qualifying rows: nothing is guessed into
    items (guards against unrelated 4-column tables)."""
    table = [["Only Row", "1", "5.00", "5.00"]]
    items, summary = extract_line_items([table])
    assert items == [] and summary == []


def test_totals_only_headerless_table_unchanged():
    """TC-S2-L05 semantics preserved in the fallback path: a totals-only
    headerless table yields zero items and no fabricated summary."""
    table = [["Subtotal", "$5.00"], ["Grand Total", "$5.00"]]
    items, summary = extract_line_items([table])
    assert items == [] and summary == []


def test_cgst_sgst_igst_summary_rows_not_items_and_tax_labelled():
    """TC-E6-L07 — CGST/SGST/IGST rows in a headered four-column table are
    summary rows (never items), and CGST is recognised as a tax label in
    the text layer."""
    table = CPS_TABLE + [
        ["", "", "CGST", "INR 3,273.78"],
        ["", "", "SGST", "INR 3,273.78"],
    ]
    items, summary = extract_line_items([table])
    assert len(items) == 5
    for row in summary:
        assert row[0] in ("CGST", "SGST", "Subtotal", "Discount", "GST (18%)",
                          "Total")
    assert ("CGST", "INR 3,273.78") in summary
    assert ("SGST", "INR 3,273.78") in summary


def test_cgst_sgst_summed_in_text_layer():
    """TC-E6-L08 — CGST/SGST labels feed the tax strategy and their
    components are SUMMED (no combined tax row present); longest-first
    matching keeps 'gstin' safe."""
    text = """TAX INVOICE
Acme Ltd Invoice No: X-100
Invoice Date: 2026-01-02
Subtotal 1000.00
CGST 90.00
SGST 90.00
Total 1180.00"""
    fields = build_fields(text, [])
    assert fields["tax"]["status"] == "found"
    assert fields["tax"]["value"] == Decimal("180.00")


def test_igst_only_row_is_the_tax():
    """TC-E6-L09 — IGST-only invoice: tax is the IGST amount."""
    text = """TAX INVOICE
Acme Ltd Invoice No: X-101
Invoice Date: 2026-01-02
Subtotal 1000.00
IGST 180.00
Total 1180.00"""
    fields = build_fields(text, [])
    assert fields["tax"]["status"] == "found"
    assert fields["tax"]["value"] == Decimal("180.00")


def test_combined_gst_row_wins_over_components():
    """TC-E6-L10 — no double counting: when a combined tax row exists
    alongside CGST/SGST components, the combined row is the tax."""
    text = """TAX INVOICE
Acme Ltd Invoice No: X-102
Invoice Date: 2026-01-02
Subtotal 1000.00
CGST 90.00
SGST 90.00
Total Tax 180.00"""
    fields = build_fields(text, [])
    assert fields["tax"]["status"] == "found"
    assert fields["tax"]["value"] == Decimal("180.00")
