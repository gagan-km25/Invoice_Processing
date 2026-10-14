"""Sprint 3 unit tests — review validation service (pure functions).
IDs TC-S3-U01… (catalogued in docs/04)."""
from decimal import Decimal

from app.services.review import (
    parse_line_rows,
    prefill_from_draft,
    validate_and_merge,
    with_blank_rows,
)


def base_form(**overrides):
    form = {
        "vendor": "Acme Corporation",
        "vendor_tax_id": "",
        "invoice_number": "INV-1",
        "invoice_date": "2026-01-15",
        "due_date": "",
        "bill_to": "",
        "currency": "",
        "subtotal": "100.00",
        "discount": "",
        "tax": "",
        "tax_rate": "",
        "total": "100.00",
    }
    form.update(overrides)
    return form


def test_minimal_valid_form():
    """TC-S3-U01 — required fields only: ok, Decimals quantized."""
    result = validate_and_merge(base_form())
    assert result["ok"] is True and result["errors"] == {}
    assert result["data"]["header"]["subtotal"] == Decimal("100.00")
    assert result["data"]["header"]["total"] == Decimal("100.00")
    assert result["data"]["lines"] == []


def test_missing_required_fields_blocked():
    """TC-S3-U02 — blank invoice_number / invoice_date / subtotal / total."""
    result = validate_and_merge(base_form(invoice_number="  ", invoice_date="",
                                          subtotal="", total=""))
    assert result["ok"] is False
    for name in ("invoice_number", "invoice_date", "subtotal", "total"):
        assert name in result["errors"], name


def test_bad_date_format_blocked():
    """TC-S3-U03 — '15/01/2026' is not YYYY-MM-DD → blocked, format named."""
    result = validate_and_merge(base_form(invoice_date="15/01/2026"))
    assert result["ok"] is False
    assert "YYYY-MM-DD" in result["errors"]["invoice_date"]


def test_due_before_invoice_warns_not_blocks():
    """TC-S3-U04 — due date earlier than invoice date: warning, save allowed."""
    result = validate_and_merge(base_form(due_date="2026-01-10"))
    assert result["ok"] is True
    assert any("earlier than the invoice date" in w for w in result["warnings"])


def test_decimal_quantized():
    """TC-S3-U05 — '1250.5' accepted and quantized to 1250.50."""
    result = validate_and_merge(base_form(subtotal="1250.5", total="1250.5"))
    assert result["data"]["header"]["subtotal"] == Decimal("1250.50")


def test_non_decimal_blocked():
    """TC-S3-U06 — non-numeric amount blocked, field named."""
    result = validate_and_merge(base_form(subtotal="lots"))
    assert result["ok"] is False
    assert "must be a number" in result["errors"]["subtotal"]


def test_currency_rules():
    """TC-S3-U07 — 3-letter code uppercased; wrong length blocked; blank ok."""
    ok = validate_and_merge(base_form(currency="usd"))
    assert ok["data"]["header"]["currency"] == "USD"
    bad = validate_and_merge(base_form(currency="euros"))
    assert bad["ok"] is False and "currency" in bad["errors"]
    blank = validate_and_merge(base_form(currency=""))
    assert blank["data"]["header"]["currency"] is None


def test_quantity_must_be_positive():
    """TC-S3-U08 — quantity 0 or negative blocked, row named."""
    form = base_form()
    form.update({"description_0": "Widget", "quantity_0": "0",
                 "unit_price_0": "5", "amount_0": "0"})
    result = validate_and_merge(form)
    assert result["ok"] is False
    assert "above 0" in result["errors"]["quantity_0"]


def test_unit_price_negative_blocked():
    """TC-S3-U09 — negative unit price blocked."""
    form = base_form()
    form.update({"description_0": "Widget", "quantity_0": "1",
                 "unit_price_0": "-2", "amount_0": "-2"})
    result = validate_and_merge(form)
    assert "unit_price_0" in result["errors"]


def test_blank_rows_ignored():
    """TC-S3-U10 — fully blank rows are dropped silently (AC-03.4)."""
    form = base_form()
    form.update({"description_0": "", "quantity_0": "", "unit_price_0": "",
                 "amount_0": ""})
    result = validate_and_merge(form)
    assert result["ok"] is True and result["data"]["lines"] == []


def test_removed_row_dropped():
    """TC-S3-U11 — ticked remove checkbox drops the row."""
    form = base_form()
    form.update({"description_0": "Widget", "quantity_0": "1",
                 "unit_price_0": "5", "amount_0": "5",
                 "remove_0": "on"})
    result = validate_and_merge(form)
    assert result["data"]["lines"] == []


def test_partial_row_requires_description():
    """TC-S3-U12 — row with numbers but no description → error, not dropped."""
    form = base_form()
    form.update({"description_0": "", "quantity_0": "1",
                 "unit_price_0": "5", "amount_0": "5"})
    result = validate_and_merge(form)
    assert result["ok"] is False
    assert "description_0" in result["errors"]


def test_line_amount_mismatch_warns():
    """TC-S3-U13 — amount ≠ qty × unit price: warning, save allowed."""
    form = base_form()
    form.update({"description_0": "Widget", "quantity_0": "2",
                 "unit_price_0": "5", "amount_0": "99"})
    result = validate_and_merge(form)
    assert result["ok"] is True
    assert any("does not match quantity" in w for w in result["warnings"])


def test_totals_mismatch_warns():
    """TC-S3-U14 — subtotal+tax ≠ total: warning, save allowed (E-16)."""
    result = validate_and_merge(base_form(tax="8.00"))
    assert result["ok"] is True
    assert any("does not match the total" in w for w in result["warnings"])


def test_lines_renumbered_sequentially():
    """TC-S3-U15 — kept lines get line_number 1..n in submitted order."""
    form = base_form()
    form.update({
        "description_5": "Second", "quantity_5": "1", "unit_price_5": "1",
        "amount_5": "1",
        "description_2": "First", "quantity_2": "1", "unit_price_2": "1",
        "amount_2": "1",
    })
    result = validate_and_merge(form)
    numbers = [line["line_number"] for line in result["data"]["lines"]]
    descriptions = [line["description"] for line in result["data"]["lines"]]
    assert numbers == [1, 2]
    assert descriptions == ["First", "Second"]  # index order: 2 before 5


def test_long_text_rejected():
    """TC-S3-U16 — free-text fields capped at 200 characters."""
    result = validate_and_merge(base_form(vendor="x" * 201))
    assert result["ok"] is False and "vendor" in result["errors"]


def test_empty_form_all_required_errors():
    """TC-S3-U17 — empty submission: ok=False with the four required errors."""
    result = validate_and_merge({})
    assert result["ok"] is False
    assert set(result["errors"]) >= {"invoice_number", "invoice_date",
                                     "subtotal", "total"}


def test_prefill_from_draft():
    """TC-S3-U18 — GET prefill: values stringified, missing → blank, flags kept."""
    draft = {
        "fields": {
            "vendor": {"status": "found", "value": "Acme"},
            "total": {"status": "ambiguous", "value": Decimal("9.00")},
            "invoice_number": {"status": "missing", "value": None},
        },
        "lines": [{"description": "Widget", "quantity": Decimal("2.00"),
                   "unit_price": Decimal("5.00"), "amount": Decimal("10.00"),
                   "line_number": 1}],
    }
    values, line_rows, flags = prefill_from_draft(draft)
    assert values["vendor"] == "Acme"
    assert values["total"] == "9.00"
    assert values["invoice_number"] == ""
    assert flags["total"] == "ambiguous"
    assert line_rows[0]["quantity"] == "2.00"


def test_with_blank_rows_appends_slots():
    """TC-S3-U19 — blank-row slots continue the index sequence."""
    rows = with_blank_rows([{"i": 0, "description": "x", "quantity": "",
                             "unit_price": "", "amount": "", "remove": False}], 3)
    assert [row["i"] for row in rows] == [0, 1, 2, 3]
    assert rows[1]["description"] == ""


def test_parse_line_rows_preserves_input():
    """TC-S3-U20 — form round-trip keeps user input for re-render."""
    form = {"description_0": "Kept", "quantity_0": "1", "unit_price_0": "2",
            "amount_0": "2", "remove_0": "on"}
    rows = parse_line_rows(form)
    assert rows == [{"i": 0, "remove": True, "description": "Kept",
                     "quantity": "1", "unit_price": "2", "amount": "2",
                     "tax": ""}]


# ------------------------------------------------ Sprint E3: §6 extensions

def test_prefill_populates_extended_fields():
    """TC-E3-XF-01 — extended header fields and per-line tax prefill the
    review form; missing fields render blank (US-E3-3 AC5 evidence)."""
    draft = {
        "fields": {
            "po_number": {"status": "found", "value": "PO-2026-77"},
            "bill_to_address": {"status": "found", "value": "42 MG Road"},
            "ship_to_name": {"status": "found", "value": "Acme Warehouse"},
            "ship_to_address": {"status": "missing", "value": None},
            "vendor_tax_id": {"status": "found", "value": "29AABCT1234F1Z5"},
        },
        "lines": [{"description": "Widget", "quantity": "2",
                   "unit_price": "50", "amount": "100", "tax": "3.5"}],
    }
    values, line_rows, _flags = prefill_from_draft(draft)
    assert values["po_number"] == "PO-2026-77"
    assert values["bill_to_address"] == "42 MG Road"
    assert values["ship_to_name"] == "Acme Warehouse"
    assert values["ship_to_address"] == ""
    assert values["vendor_tax_id"] == "29AABCT1234F1Z5"
    assert line_rows[0]["tax"] == "3.5"


def test_extended_text_fields_too_long_blocked():
    """TC-E3-XF-02 — the 200-character cap applies to extended text
    fields (po_number, vendor_tax_id), same as core text fields."""
    result = validate_and_merge(base_form(po_number="x" * 201))
    assert result["ok"] is False and "po_number" in result["errors"]
    result = validate_and_merge(base_form(vendor_tax_id="x" * 201))
    assert result["ok"] is False and "vendor_tax_id" in result["errors"]


def test_blank_extended_fields_are_valid():
    """TC-E3-XF-03 — extended fields are optional: the minimal form stays
    valid with every extended field blank."""
    result = validate_and_merge(base_form())
    assert result["ok"] is True


def test_line_tax_round_trips_and_quantizes():
    """TC-E3-XF-04 — a valid per-line tax survives validation, quantized
    to 2dp like every amount."""
    form = base_form()
    form.update({"description_0": "Widget", "quantity_0": "2",
                 "unit_price_0": "50", "amount_0": "100", "tax_0": "3.456"})
    result = validate_and_merge(form)
    assert result["ok"] is True
    assert result["data"]["lines"][0]["tax"] == Decimal("3.46")


def test_blank_line_tax_is_valid():
    """TC-E3-XF-05 — per-line tax is optional: no tax input → None."""
    form = base_form()
    form.update({"description_0": "Widget", "quantity_0": "2",
                 "unit_price_0": "50", "amount_0": "100"})
    result = validate_and_merge(form)
    assert result["ok"] is True
    assert result["data"]["lines"][0]["tax"] is None


def test_non_numeric_line_tax_blocked():
    """TC-E3-XF-06 — non-numeric per-line tax is blocked with the field
    named, per the existing decimal-field rule (AC-04.2: "non-numeric →
    blocked, field named") and US-E3-3 strict validation."""
    form = base_form()
    form.update({"description_0": "Widget", "quantity_0": "2",
                 "unit_price_0": "50", "amount_0": "100", "tax_0": "abc"})
    result = validate_and_merge(form)
    assert result["ok"] is False
    assert "tax_0" in result["errors"]
