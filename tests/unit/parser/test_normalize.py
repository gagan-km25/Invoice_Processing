"""Sprint 2 unit tests — normalization primitives (dates, amounts, currency,
invoice numbers, whitespace). IDs TC-S2-N01… (catalogued in docs/04).
"""
import pytest

from decimal import Decimal

from app.services.parser.normalize import (
    clean,
    detect_currency_symbol,
    parse_amount,
    parse_date,
    parse_invoice_number,
    resolve_currency,
)


# ---------------------------------------------------------------- dates

def test_date_dd_mon_yyyy():
    """TC-S2-N01 — the real sample format 06-Oct-2026."""
    assert parse_date("06-Oct-2026") == ("2026-10-06", "found")


def test_date_iso():
    """TC-S2-N02 — ISO input."""
    assert parse_date("2026-01-15") == ("2026-01-15", "found")


def test_date_us_textual():
    """TC-S2-N03 — 'Mar 4, 2025'."""
    assert parse_date("Mar 4, 2025") == ("2025-03-04", "found")


def test_date_eu_textual():
    """TC-S2-N04 — '4 Mar 2025'."""
    assert parse_date("4 Mar 2025") == ("2025-03-04", "found")


def test_date_numeric_slash_ambiguous():
    """TC-S2-N05 — 03/04/2025 is flagged, never silently trusted (AC-2.4)."""
    assert parse_date("03/04/2025") == ("2025-03-04", "ambiguous")


def test_date_numeric_slash_day_beyond_twelve():
    """TC-S2-N06 — 25/03/2025 cannot be month-first → unambiguous D/M."""
    assert parse_date("25/03/2025") == ("2025-03-25", "found")


def test_date_prose_is_missing():
    """TC-S2-N07 — 'Due on receipt' is not a date (exploration finding 3)."""
    assert parse_date("Due on receipt") == (None, "missing")


def test_date_empty_is_missing():
    """TC-S2-N08 — empty/None."""
    assert parse_date("") == (None, "missing")
    assert parse_date(None) == (None, "missing")


# -------------------------------------------------------------- amounts

def test_amount_mojibake_glyph():
    """TC-S2-N09 — real-sample pattern 'n1,250.00' (rupee glyph corruption)."""
    assert parse_amount("n1,250.00") == Decimal("1250.00")


def test_amount_dollar():
    """TC-S2-N10 — '$1,234.56'."""
    assert parse_amount("$1,234.56") == Decimal("1234.56")


def test_amount_european():
    """TC-S2-N11 — European decimal comma."""
    assert parse_amount("1.234,56") == Decimal("1234.56")


def test_amount_parentheses_negative():
    """TC-S2-N12 — accounting negative (E-14)."""
    assert parse_amount("(123.45)") == Decimal("-123.45")


def test_amount_zero():
    """TC-S2-N13 — zero discount value is a real value, not missing."""
    assert parse_amount("n0.00") == Decimal("0.00")


def test_amount_plain_integer():
    """TC-S2-N16 — bare quantity integer quantizes to 2 dp."""
    assert parse_amount("12") == Decimal("12.00")


def test_amount_garbage_is_none():
    """TC-S2-N15 — non-numeric junk → None."""
    assert parse_amount("n/a") is None
    assert parse_amount("") is None
    assert parse_amount(None) is None


# ------------------------------------------------------------ currency

def test_currency_known_symbol():
    """TC-S2-N17 — '$' maps to USD as found."""
    assert resolve_currency(["$"], False) == ("USD", "found", None)


def test_currency_rupee_symbol():
    """TC-S2-N18 — a properly encoded '₹' maps to INR."""
    assert resolve_currency(["₹"], False) == ("INR", "found", None)


def test_currency_mojibake_with_gst_context():
    """TC-S2-N19 — 'n' glyph + GSTIN → INR but flagged ambiguous (FR-6)."""
    value, status, evidence = resolve_currency(["n"], True)
    assert (value, status) == ("INR", "ambiguous")
    assert "GSTIN" in evidence


def test_currency_mojibake_without_context():
    """TC-S2-N20 — 'n' glyph alone: ambiguous, no value invented."""
    value, status, _ = resolve_currency(["n"], False)
    assert value is None and status == "ambiguous"


def test_currency_nothing_seen():
    """TC-S2-N21 — no symbol evidence → missing."""
    assert resolve_currency([None], False) == (None, "missing", None)


def test_currency_symbol_detection():
    """TC-S2-N22 — symbol detector on amount tokens (and not on prose)."""
    assert detect_currency_symbol("n1,250.00") == "n"
    assert detect_currency_symbol("$1,234.56") == "$"
    assert detect_currency_symbol("Subtotal n6,550.00") is None  # full line: no


# ------------------------------------------------------ invoice numbers

def test_invoice_number_plain():
    """TC-S2-N23 — real sample number."""
    assert parse_invoice_number("TN-2026-1001") == "TN-2026-1001"


def test_invoice_number_slashes_uppercased():
    """TC-S2-N24 — GLF/26/4078 (exploration: slash-safe, E-17)."""
    assert parse_invoice_number("glf/26/4078") == "GLF/26/4078"


def test_invoice_number_requires_digit():
    """TC-S2-N25 — prose like 'due' must never parse as a number."""
    assert parse_invoice_number("due on receipt") is None


# ----------------------------------------------------------- whitespace

def test_clean_collapses_whitespace():
    """TC-S2-N27 — runs, tabs, NBSP collapse to single spaces."""
    assert clean("  a\t\tb  c  d ") == "a b c d"


# ------------------------------------------------- Sprint E6: INR
# currency tokens, Indian digit grouping, comma-group disambiguation.


@pytest.mark.parametrize("text,expected", [
    ("Rs. 1,25,000.00", "125000.00"),   # G1: 'Rs.' dot artefact
    ("₹1,25,000.00", "125000.00"),      # glyph + Indian grouping
    ("INR 4,500.00", "4500.00"),        # word token + grouping
    ("INR32,200.00", "32200.00"),       # glued word token
    ("Rs 500", "500.00"),               # space-separated token
    ("1,25,000.00", "125000.00"),       # bare Indian grouping
    ("32,200.00", "32200.00"),
    ("$1,234.56", "1234.56"),           # US preserved
    ("1.234,56", "1234.56"),            # European preserved
])
def test_parse_amount_indian_and_existing_formats(text, expected):
    assert parse_amount(text) == Decimal(expected)


@pytest.mark.parametrize("text,expected", [
    ("₹1,25,000.00", "₹"),          # glyph + Indian grouping (was None)
    ("Rs. 500", "Rs."),             # word token (was None)
    ("Rs 500", "Rs."),              # word token, no dot (was None)
    ("INR 4,500.00", "INR"),        # ISO word token (was None)
    ("INR32,200.00", "INR"),        # glued ISO token (was None)
    ("n1,250.00", "n"),             # mojibake pattern preserved
    ("$1,234.56", "$"),             # glyph preserved
])
def test_detect_currency_symbol_tokens(text, expected):
    assert detect_currency_symbol(text) == expected


def test_detect_ignores_labels_and_plain_numbers():
    """'Currency: INR' is handled by the label rule, not the amount-token
    detector; plain numbers carry no signal."""
    assert detect_currency_symbol("Currency: INR") is None
    assert detect_currency_symbol("32,200.00") is None


@pytest.mark.parametrize("text,expected", [
    ("13,200", "13200"),       # zero-decimal grouped: thousands, not 13.2
    ("12,000", "12000"),       # same rule
    ("1,25,000", "125000"),    # Indian grouping without decimals
    ("12,5", "12.50"),         # 1-digit final group → decimal comma
    ("1.234,56", "1234.56"),   # European decimal comma (2-digit group)
])
def test_comma_group_disambiguation(text, expected):
    """The final comma group is a decimal separator only when it has ≤2
    digits; 3-digit groups are thousands separators (zero-decimal and
    Indian-grouping safety rule, Sprint E6)."""
    assert parse_amount(text) == Decimal(expected)
