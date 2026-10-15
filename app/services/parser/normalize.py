"""Normalization primitives: whitespace, dates, amounts, currency, tokens.

Pure functions only — no I/O, no Flask, no PDF specifics (architecture rule).
Money handling uses decimal.Decimal at the boundary and quantizes to 0.01
(decision M-3).
"""
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

_WHITESPACE = re.compile(r"\s+")

ISO_CODES = {"USD", "EUR", "GBP", "INR", "AUD", "CAD", "SGD", "AED", "JPY"}
SYMBOL_TO_CODE = {
    "$": "USD", "€": "EUR", "£": "GBP", "₹": "INR", "¥": "JPY",
    "INR": "INR", "Rs.": "INR", "Rs": "INR",
}


def clean(value) -> str:
    """Collapse all whitespace runs (incl. non-breaking spaces) to one space."""
    if value is None:
        return ""
    return _WHITESPACE.sub(" ", str(value)).strip()


def text_lines(text: str) -> list[str]:
    """Non-empty, whitespace-collapsed lines, in document order."""
    return [line for raw in (text or "").splitlines() if (line := clean(raw))]


# --------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------

# (format, is_numeric_slash_date) — numeric slash dates are read US-first and
# flagged ambiguous when both readings are plausible (AC-2.4).
_DATE_FORMATS = [
    ("%d-%b-%Y", False),
    ("%d-%b-%y", False),
    ("%d-%B-%Y", False),
    ("%Y-%m-%d", False),
    ("%d %b %Y", False),
    ("%d %B %Y", False),
    ("%b %d, %Y", False),
    ("%B %d, %Y", False),
    ("%m/%d/%Y", True),
    ("%m/%d/%y", True),
    ("%d/%m/%Y", False),  # only reached when month-first reading is impossible
]


def parse_date(value) -> tuple[str | None, str]:
    """Parse a date string → (ISO 'YYYY-MM-DD' | None, status).

    status: 'found' | 'ambiguous' | 'missing'. Ambiguous means the value was
    interpreted with the US month-first default but the day/month swap is also
    plausible — flagged, never silently trusted.
    """
    text = clean(value)
    if not text:
        return None, "missing"
    for fmt, is_slash in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt).date()
        except ValueError:
            continue
        if is_slash:
            month_part, day_part, _ = text.split("/")
            if int(day_part) <= 12 and int(month_part) <= 12:
                return parsed.isoformat(), "ambiguous"
        return parsed.isoformat(), "found"
    return None, "missing"


# --------------------------------------------------------------------------
# Amounts
# --------------------------------------------------------------------------


def parse_amount(value) -> Decimal | None:
    """Parse an amount token → Decimal quantized to 0.01, or None.

    Handles: attached currency glyphs ('n1,250.00' — mojibake — or '$1,234.56'),
    thousands separators in US and European order, parentheses negatives.
    """
    text = clean(value)
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    text = re.sub(r"[^0-9,.\-]", "", text)  # drop symbols/letters/glyphs
    text = text.lstrip(".,")  # 'Rs. 1,25,000.00' leaves '.125000.00' here
    if not re.search(r"\d", text):
        return None
    last_dot, last_comma = text.rfind("."), text.rfind(",")
    if last_comma > last_dot:
        # European decimal comma: 1.234,56 — but ONLY when the final comma
        # group is a plausible decimal (≤2 digits). '13,200' (3 digits) is a
        # thousands separator, not 13.2 (verified: zero-decimal JPY amounts).
        if len(text) - last_comma - 1 <= 2:
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    else:  # US: 1,234.56
        text = text.replace(",", "")
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return None
    if negative:
        amount = -amount
    return amount.quantize(Decimal("0.01"))


def detect_currency_symbol(amount_text) -> str | None:
    """A currency token attached to an amount.

    Recognised: single glyphs with US-grouped or Indian-grouped digits
    ('$1,234.56', '₹1,25,000.00'), word tokens ('INR 4,500.00', 'Rs. 500',
    'Rs.1,25,000.00'), the mojibake pattern ('n1250.00' — bare letter glued
    to a well-formed number, never in prose), and a trailing glyph
    ('1,179.00 ₹').
    """
    text = clean(amount_text)
    match = re.match(r"^(INR|RS\.?)\s*(?=\d)", text, re.IGNORECASE)
    if match:
        token = match.group(1).upper()
        return {"RS": "Rs.", "RS.": "Rs."}.get(token, token)
    match = re.match(r"^([$€£₹¥])\s*(?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d{2})?$", text)
    if match:
        return match.group(1)
    match = re.match(r"^([A-Za-z])\s*\d{1,3}(?:[,\.\ ]\d{3})*(?:\.\d{2})?$", text)
    if match:
        return match.group(1)
    match = re.search(r"\d(?:[,\.\ ]\d{3})*(?:\.\d{2})?\s*([$€£₹¥])$", text)
    if match:
        return match.group(1)
    return None


def resolve_currency(
    seen_symbols: list[str | None], has_gst_context: bool
) -> tuple[str | None, str, str | None]:
    """Resolve (value, status, evidence) from observed amount symbols.

    Priority: known symbol → code; ISO code → found; unknown glyph + GST
    context → INR flagged ambiguous (evidence recorded); unknown glyph alone →
    ambiguous with raw glyph; nothing → missing.
    """
    if "¥" in seen_symbols:
        # Ambiguous symbol (JPY vs CNY) — never guessed (Sprint E6).
        return (
            "JPY",
            "ambiguous",
            "¥ symbol denotes JPY or CNY — please confirm",
        )
    for symbol in seen_symbols:
        if not symbol:
            continue
        if symbol.upper() in ISO_CODES:
            return symbol.upper(), "found", None
    for symbol in seen_symbols:
        if symbol and symbol in SYMBOL_TO_CODE:
            return SYMBOL_TO_CODE[symbol], "found", None
    unknown = [s for s in seen_symbols if s]
    if unknown:
        if has_gst_context:
            return (
                "INR",
                "ambiguous",
                f"unmapped currency glyph {unknown[0]!r} on amounts; "
                "GSTIN/GST present, so INR inferred — please confirm",
            )
        return None, "ambiguous", f"unmapped currency glyph {unknown[0]!r} on amounts"
    return None, "missing", None


# --------------------------------------------------------------------------
# Tokens
# --------------------------------------------------------------------------


def parse_invoice_number(value) -> str | None:
    """First invoice-number-like token: letters/digits/-//, must contain a
    digit (so prose like 'due' never parses as a number). Slash-safe (E-17)."""
    text = clean(value)
    if not text:
        return None
    match = re.search(r"[A-Za-z0-9][A-Za-z0-9/-]*\d[A-Za-z0-9/-]*", text)
    return match.group(0).upper() if match else None
