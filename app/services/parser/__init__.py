"""Invoice field parser — public API.

parse(text, tables, page_count) → Draft dict (see docs/07 §Phase B).

Pure functions only: text/tables in, structured draft out. No file, database,
or Flask access from this package, ever. Every field strategy is guarded — a
strategy exception marks that field missing instead of aborting the parse, and
garbage input yields an all-missing draft, never an exception (NFR-4, AC-2.3).
"""
from decimal import Decimal

from . import currencies, fields as _fields
from .lines import extract_line_items
from .normalize import clean

PARSER_VERSION = 1

HEADER_FIELDS = (
    "vendor",
    "vendor_tax_id",
    "invoice_number",
    "invoice_date",
    "due_date",
    "bill_to",
    "currency",
    "subtotal",
    "discount",
    "tax_rate",
    "tax",
    "total",
)


def _guarded(strategy):
    """Run a field strategy; an exception becomes a missing field + note."""
    def run(*args, **kwargs):
        try:
            return strategy(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 — deliberate containment
            return _fields.missing(note=f"strategy error: {exc}")
    return run


def _consistency_checks(fields: dict, lines: list[dict]) -> list[dict]:
    checks: list[dict] = []
    subtotal = _value(fields.get("subtotal"))
    discount = _value(fields.get("discount"))
    tax = _value(fields.get("tax"))
    total = _value(fields.get("total"))

    if None not in (subtotal, tax, total):
        base = subtotal - (discount if discount is not None else Decimal("0.00"))
        expected = base + tax
        passed = abs(expected - total) <= Decimal("0.01")
        checks.append(
            {
                "rule": "subtotal - discount + tax == total",
                "passed": passed,
                "detail": f"computed {expected}, invoice states {total}",
            }
        )
    invoice_date = _value(fields.get("invoice_date"))
    due_date = _value(fields.get("due_date"))
    if invoice_date and due_date:
        checks.append(
            {
                "rule": "due_date >= invoice_date",
                "passed": due_date >= invoice_date,
                "detail": f"due {due_date}, invoice {invoice_date}",
            }
        )
    if lines:
        expected_sum = sum(
            (line["amount"] for line in lines if line["amount"] is not None),
            Decimal("0.00"),
        )
        if subtotal is not None:
            passed = abs(expected_sum - subtotal) <= Decimal("0.01")
            checks.append(
                {
                    "rule": "line items sum == subtotal",
                    "passed": passed,
                    "detail": f"lines {expected_sum}, subtotal {subtotal}",
                }
            )
    return checks


def _value(field) -> Decimal | str | None:
    if not field or field.get("status") == "missing":
        return None
    return field.get("value")


def parse(text: str, tables: list, page_count: int | None = None) -> dict:
    """Parse raw extraction views into a normalized draft."""
    safe_fields = _guarded(_fields.build_fields)(text or "", tables)
    safe_lines = _guarded(extract_line_items)(tables)

    draft: dict = {
        "fields": {},
        "vendor_address": None,
        "lines": [],
        "checks": [],
        "meta": {"page_count": page_count, "parser_version": PARSER_VERSION},
    }

    for name in HEADER_FIELDS:
        draft["fields"][name] = safe_fields.get(name) or _fields.missing()
    vendor_address = safe_fields.get("_vendor_address")
    if vendor_address and vendor_address.get("status") == "found":
        draft["vendor_address"] = clean(vendor_address.get("value"))

    items, _summary = safe_lines if isinstance(safe_lines, tuple) else ([], [])
    draft["lines"] = [
        {
            "line_number": item["line_number"],
            "description": item["description"],
            "quantity": item["quantity"],
            "unit_price": item["unit_price"],
            "amount": item["amount"],
        }
        for item in items
    ]
    draft["checks"] = _consistency_checks(draft["fields"], draft["lines"])

    # Zero-decimal currencies: requantize line amounts to the currency's
    # minor-unit exponent (JPY → 0 decimals, not forced to 2). F1: only on
    # a CONFIRMED currency — ambiguous values never requantize.
    currency_field = draft["fields"].get("currency") or {}
    code = currency_field.get("value") if currency_field.get("status") == "found" else None
    exponent = currencies.exponent_for(code) if code else None
    if exponent is not None and exponent != 2:
        quantum = Decimal(1).scaleb(-exponent)
        for line in draft["lines"]:
            for key in ("unit_price", "amount"):
                if isinstance(line.get(key), Decimal):
                    line[key] = line[key].quantize(quantum)
    return draft
