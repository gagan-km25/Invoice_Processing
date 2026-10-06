"""Sprint 2 unit tests — parser robustness: garbage in never crashes, never
invents values (NFR-4, AC-2.3, US-2). IDs TC-S2-R01…"""
from app.services.parser import parse

ALL_FIELDS = (
    "vendor", "vendor_tax_id", "invoice_number", "invoice_date", "due_date",
    "bill_to", "currency", "subtotal", "discount", "tax_rate", "tax", "total",
)


def _assert_all_missing(draft):
    for name in ALL_FIELDS:
        assert draft["fields"][name]["status"] == "missing", name
    assert draft["lines"] == []


def test_empty_input():
    """TC-S2-R01 — completely empty input."""
    draft = parse("", [])
    _assert_all_missing(draft)
    assert draft["meta"]["page_count"] is None


def test_garbage_text():
    """TC-S2-R02 — random prose/numbers must produce missing, not guesses."""
    draft = parse("Lorem ipsum 123 dolor sit amet 45.67 amet", [])
    _assert_all_missing(draft)


def test_none_tables_and_none_text():
    """TC-S2-R03 — None inputs tolerated (service layer may pass degraded views)."""
    draft = parse(None, None)
    _assert_all_missing(draft)


def test_unicode_and_control_characters():
    """TC-S2-R04 — emoji, RTL marks, zero-width chars: no crash, no fields."""
    weird = "​ begin \U0001f600 ‫text‬ \x00\x01 end"
    draft = parse(weird, [])
    _assert_all_missing(draft)


def test_table_with_none_cells():
    """TC-S2-R05 — ragged/None cells in tables must not crash."""
    tables = [[[None, None], ["Bill To:", None]], [[None]]]
    draft = parse("INVOICE", tables)
    assert draft["fields"]["vendor"]["status"] == "missing"


def test_strategy_exception_contained(monkeypatch):
    """TC-S2-R06 — a crashing strategy marks ITS field missing (with note);
    every other field still parses. Containment is per strategy."""
    from app.services.parser import fields as fields_module

    def explode(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(fields_module, "extract_tax_id", explode)
    draft = parse("Subtotal $1.00\nTotal $1.00", [])
    assert draft["fields"]["vendor_tax_id"]["status"] == "missing"
    assert "boom" in draft["fields"]["vendor_tax_id"]["note"]
    # the crash did not blank the rest of the parse:
    assert draft["fields"]["subtotal"]["value"] == "1.00" or str(
        draft["fields"]["subtotal"]["value"]
    ) in ("1.00", "1")
    assert str(draft["fields"]["total"]["value"]) in ("1.00", "1")


def test_meta_recorded():
    """TC-S2-R07 — page count and parser version recorded in meta."""
    draft = parse("INVOICE", [], page_count=3)
    assert draft["meta"]["page_count"] == 3
    assert draft["meta"]["parser_version"] >= 1
