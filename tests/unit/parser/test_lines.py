"""Sprint 2 unit tests — line-item extraction from tables. IDs TC-S2-L01…"""
from decimal import Decimal

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
