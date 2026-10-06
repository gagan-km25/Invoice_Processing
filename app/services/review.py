"""Review-stage validation and merge (Sprint 3).

Pure functions: form data in → validated save-data / errors / warnings out.
No SQL, no Flask objects required (works on any Mapping, e.g. werkzeug's
MultiDict) — unit-testable without the app (architecture rule).

Rules per approved design (docs/08 §4):
- required: invoice_number, invoice_date, subtotal, total
- decimals via parser.normalize.parse_amount (single source of truth),
  quantized to 0.01; quantity > 0; unit_price ≥ 0; tax_rate 0–100
- dates strictly YYYY-MM-DD; due < invoice → warning, save allowed (E-16)
- currency: 3-letter code or blank
- line amount vs qty×unit and totals consistency → warnings, save allowed
- blank line rows silently dropped; removed rows dropped; lines renumbered 1..n
"""
import re
from datetime import datetime
from decimal import Decimal

from app.services.parser.normalize import parse_amount

MAX_TEXT = 200
DATE_FORMAT = "%Y-%m-%d"

HEADER_TEXT_FIELDS = (
    "vendor",
    "vendor_tax_id",
    "invoice_number",
    "bill_to",
)
DATE_FIELDS = ("invoice_date", "due_date")
MONEY_FIELDS = ("subtotal", "discount", "tax", "total")
REQUIRED = ("invoice_number", "invoice_date", "subtotal", "total")

_LINE_INDEX = re.compile(r"description_(\d+)$")
_CURRENCY = re.compile(r"^[A-Za-z]{3}$")


def _clean(value) -> str:
    return (value or "").strip() if isinstance(value, str) else ("" if value is None else str(value).strip())


def parse_line_rows(form) -> list[dict]:
    """Reconstruct line rows from indexed field names, preserving the user's
    input and original row indices (used for re-render after errors)."""
    indices = sorted(
        int(match.group(1))
        for key in form.keys()
        if (match := _LINE_INDEX.match(key))
    )
    rows = []
    for i in indices:
        rows.append(
            {
                "i": i,
                "remove": bool(form.get(f"remove_{i}")),
                "description": _clean(form.get(f"description_{i}")),
                "quantity": _clean(form.get(f"quantity_{i}")),
                "unit_price": _clean(form.get(f"unit_price_{i}")),
                "amount": _clean(form.get(f"amount_{i}")),
            }
        )
    return rows


def _validate_text(fields: dict, errors: dict) -> None:
    for name in HEADER_TEXT_FIELDS:
        value = _clean(fields.get(name))
        if len(value) > MAX_TEXT:
            errors[name] = "Value is too long (max 200 characters)."
            continue
        if name == "invoice_number" and not value:
            errors[name] = "Invoice number is required."
        elif value:
            fields[name] = value
        else:
            fields[name] = None


def _validate_dates(fields: dict, errors: dict, warnings: list) -> None:
    for name in DATE_FIELDS:
        raw = _clean(fields.get(name))
        if not raw:
            fields[name] = None
            if name == "invoice_date":
                errors[name] = "Invoice date is required (YYYY-MM-DD)."
            continue
        try:
            parsed = datetime.strptime(raw, DATE_FORMAT).date()
        except ValueError:
            errors[name] = "Use the YYYY-MM-DD date format."
            continue
        fields[name] = parsed.isoformat()
    invoice_date, due_date = fields.get("invoice_date"), fields.get("due_date")
    if invoice_date and due_date and due_date < invoice_date:
        warnings.append(
            f"Due date ({due_date}) is earlier than the invoice date "
            f"({invoice_date})."
        )


def _validate_money(fields: dict, errors: dict) -> None:
    for name in MONEY_FIELDS:
        raw = _clean(fields.get(name))
        if not raw:
            fields[name] = None
            if name in REQUIRED:
                errors[name] = f"{name.replace('_', ' ').capitalize()} is required."
            continue
        amount = parse_amount(raw)
        if amount is None:
            errors[name] = f"{name.replace('_', ' ').capitalize()} must be a number."
            fields[name] = None  # never let raw strings reach arithmetic
            continue
        if amount < 0:
            errors[name] = f"{name.replace('_', ' ').capitalize()} cannot be negative."
            fields[name] = None
            continue
        fields[name] = amount
    rate_raw = _clean(fields.get("tax_rate"))
    if not rate_raw:
        fields["tax_rate"] = None
        return
    rate = parse_amount(rate_raw)
    if rate is None or not (Decimal("0") <= rate <= Decimal("100")):
        errors["tax_rate"] = "Tax rate must be a number between 0 and 100."
    else:
        fields["tax_rate"] = rate


def _validate_currency(fields: dict, errors: dict) -> None:
    raw = _clean(fields.get("currency"))
    if not raw:
        fields["currency"] = None
    elif _CURRENCY.match(raw):
        fields["currency"] = raw.upper()
    else:
        errors["currency"] = "Currency must be a 3-letter code (e.g. USD, INR)."


def _validate_lines(form, errors: dict, warnings: list) -> list[dict]:
    kept: list[dict] = []
    for row in parse_line_rows(form):
        label = f"line {row['i'] + 1}"
        if row["remove"]:
            continue
        if not (row["description"] or row["quantity"] or row["unit_price"] or row["amount"]):
            continue  # blank row — silently ignored (AC-03.4)
        if not row["description"]:
            errors[f"description_{row['i']}"] = f"{label}: description is required."
            continue
        if len(row["description"]) > MAX_TEXT:
            errors[f"description_{row['i']}"] = f"{label}: description too long."
            continue
        quantity = parse_amount(row["quantity"])
        if quantity is None or quantity <= 0:
            errors[f"quantity_{row['i']}"] = f"{label}: quantity must be a number above 0."
            continue
        unit_price = parse_amount(row["unit_price"])
        if unit_price is None or unit_price < 0:
            errors[f"unit_price_{row['i']}"] = f"{label}: unit price must be a number ≥ 0."
            continue
        amount = parse_amount(row["amount"])
        if amount is None:
            errors[f"amount_{row['i']}"] = f"{label}: amount must be a number."
            continue
        if abs(quantity * unit_price - amount) > Decimal("0.01"):
            warnings.append(
                f"{label}: amount ({amount}) does not match quantity × unit price "
                f"({quantity * unit_price})."
            )
        kept.append(
            {
                "description": row["description"],
                "quantity": quantity,
                "unit_price": unit_price,
                "amount": amount,
            }
        )
    for number, line in enumerate(kept, start=1):
        line["line_number"] = number
    return kept


def _consistency_warnings(header: dict, warnings: list) -> None:
    subtotal, discount = header.get("subtotal"), header.get("discount")
    tax, total = header.get("tax"), header.get("total")
    if None in (subtotal, total):
        return
    discount = discount if discount is not None else Decimal("0.00")
    tax = tax if tax is not None else Decimal("0.00")
    computed = subtotal - discount + tax
    if abs(computed - total) > Decimal("0.01"):
        warnings.append(
            f"Consistency: subtotal − discount + tax ({computed}) does not match "
            f"the total ({total})."
        )


def validate_and_merge(form):
    """Validate a review-form submission.

    Returns {ok, data, errors, warnings}:
      ok      — False when any *error* exists (warnings never block, E-16)
      data    — {"header": {column: value}, "lines": [{...}]} ready for the
                repository (Decimals for money)
      errors  — {field_or_line_key: message}
      warnings — [messages] displayed but non-blocking
    """
    fields = {name: form.get(name) for name in HEADER_TEXT_FIELDS + DATE_FIELDS + MONEY_FIELDS + ("currency", "tax_rate")}
    fields = dict(fields)
    errors: dict[str, str] = {}
    warnings: list[str] = []

    _validate_text(fields, errors)
    _validate_dates(fields, errors, warnings)
    _validate_money(fields, errors)
    _validate_currency(fields, errors)
    lines = _validate_lines(form, errors, warnings)
    _consistency_warnings(fields, warnings)

    header = {
        "vendor": fields.get("vendor"),
        "vendor_tax_id": fields.get("vendor_tax_id"),
        "invoice_number": fields.get("invoice_number"),
        "invoice_date": fields.get("invoice_date"),
        "due_date": fields.get("due_date"),
        "bill_to": fields.get("bill_to"),
        "currency": fields.get("currency"),
        "subtotal": fields.get("subtotal"),
        "discount": fields.get("discount"),
        "tax": fields.get("tax"),
        "tax_rate": fields.get("tax_rate"),
        "total": fields.get("total"),
    }
    return {"ok": not errors, "data": {"header": header, "lines": lines},
            "errors": errors, "warnings": warnings}


def prefill_from_draft(draft: dict) -> tuple[dict, list[dict], dict]:
    """Build (values, line_rows, flags) for a fresh GET of the review page.

    Values come from the extraction draft; flags carry each field's extraction
    status so ambiguous/missing fields render flagged (AC-01.2).
    """
    fields = draft.get("fields", {})
    values = {}
    flags = {}
    for name in HEADER_TEXT_FIELDS + DATE_FIELDS + MONEY_FIELDS + ("currency", "tax_rate"):
        field = fields.get(name) or {}
        status = field.get("status", "missing")
        value = field.get("value") if status != "missing" else ""
        values[name] = "" if value is None else str(value)
        flags[name] = status
    line_rows = [
        {
            "i": index,
            "remove": False,
            "description": line.get("description") or "",
            "quantity": "" if line.get("quantity") is None else str(line["quantity"]),
            "unit_price": "" if line.get("unit_price") is None else str(line["unit_price"]),
            "amount": "" if line.get("amount") is None else str(line["amount"]),
        }
        for index, line in enumerate(draft.get("lines", []))
    ]
    return values, line_rows, flags


def with_blank_rows(line_rows: list[dict], extra_blanks: int = 3) -> list[dict]:
    """Append N empty rows so the review page always offers add-item slots
    (no JavaScript required; truly blank rows are ignored on save)."""
    next_index = max((row["i"] for row in line_rows), default=-1) + 1
    return line_rows + [
        {"i": next_index + offset, "remove": False, "description": "",
         "quantity": "", "unit_price": "", "amount": ""}
        for offset in range(extra_blanks)
    ]


def form_to_view(form, extra_blanks: int = 3) -> tuple[dict, list[dict]]:
    """Rebuild (values, line_rows) from a submitted form so a re-render keeps
    the user's input. Always offers a few blank rows for adding items."""
    values = {name: _clean(form.get(name)) for name in HEADER_TEXT_FIELDS + DATE_FIELDS + MONEY_FIELDS + ("currency", "tax_rate")}
    line_rows = with_blank_rows(parse_line_rows(form), extra_blanks)
    return values, line_rows
