"""Business validation engine — assignment §8.1–8.5 (Sprint E3).

Pure functions: no DB, no Flask. The pipeline calls `validate` after
extraction and persists the verdict + findings; the engine itself never
touches storage.

Severity model (approved Sprint E3 planning, decisions 1 + 4):
- Missing required fields (§8.1)                                     → error
- Amount equation mismatch beyond tolerance (§8.2):
    - no discount:   subtotal + tax = total mismatch                 → error
    - discount ≠ 0:  subtotal − discount + tax = total mismatch      → warning
  (the discount-aware variant governs discounted invoices — the assignment's
  own discounted evaluation samples, e.g. docs/07 samples 2–5, state
  subtotal − discount + tax = total; a literal subtotal + tax check would
  fail every correctly discounted invoice. Decision 1 fixes the severities:
  primary equation mismatch is an Error, discount-aware mismatch a Warning.)
- Line-item sum mismatch beyond tolerance (§8.2)                     → error
- Invoice date in the future / due date before invoice date (§8.3)   → error
- GSTIN present but not matching the 15-char format (§8.4)           → warning

Warnings never block processing (approved decision 1): verdicts `passed`
and `warning` both map to `completed`; only Error severity maps to
`validation_failed`.

Monetary precision: all arithmetic is Decimal. Amounts arrive as exact
2dp-quantized Decimals from parsing/coercion; differences are computed at
full precision and compared against the inclusive tolerance
(`diff <= tolerance` passes, `diff > tolerance` fails). No intermediate
quantization occurs inside this module.

"Today" defaults to the application's local date and is injectable for
deterministic tests (approved decision 3).
"""
import re
from datetime import date
from decimal import Decimal

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"

VERDICT_PASSED = "passed"
VERDICT_WARNING = "warning"
VERDICT_FAILED = "failed"

_GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")

_DEFAULT_TOLERANCE = Decimal("0.01")
_ZERO = Decimal("0.00")

# (field key, human label) — §8.1 mandatory fields
_MANDATORY_FIELDS = (
    ("invoice_number", "invoice number"),
    ("invoice_date", "invoice date"),
    ("vendor", "vendor name"),
    ("currency", "currency"),
    ("total", "total amount"),
)


def _finding(code, severity, message, field=None):
    finding = {"code": code, "severity": severity, "message": message}
    if field:
        finding["field"] = field
    return finding


def _raw(fields, name):
    """Draft field value (str or Decimal) when present, else None."""
    field = fields.get(name) or {}
    value = field.get("value")
    if field.get("status") in ("found", "ambiguous") and value is not None:
        return value
    return None


def _decimal(value):
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _parse_iso(value):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def validate(fields, lines, *, today=None, tolerance=_DEFAULT_TOLERANCE):
    """Validate an extracted invoice draft.

    fields: draft header fields ({name: {"status", "value"}})
    lines:  line dicts (description, quantity, unit_price, amount)
    today:  injectable date for §8.3 (default: local today)
    tolerance: inclusive amount tolerance as Decimal

    Returns {"verdict": ..., "findings": [...]} where verdict is
    passed/warning/failed and findings carry code/severity/field/message.
    """
    today = today or date.today()
    findings: list[dict] = []

    def add(code, severity, message, field=None):
        findings.append(_finding(code, severity, message, field))

    # -- R1: §8.1 mandatory fields -----------------------------------------
    for name, label in _MANDATORY_FIELDS:
        value = _raw(fields, name)
        if value in (None, ""):
            add(f"E_MISSING_{name.upper()}", SEVERITY_ERROR,
                f"{label.capitalize()} is required.", field=name)

    # numeric views for the amount rules
    subtotal = _decimal(_raw(fields, "subtotal"))
    tax = _decimal(_raw(fields, "tax"))
    total = _decimal(_raw(fields, "total"))
    discount = _decimal(_raw(fields, "discount"))

    # -- R2/R6: §8.2 amount equation ---------------------------------------
    # The applicable equation depends on the discount: subtotal + tax = total
    # when no discount applies (mismatch → Error); subtotal − discount + tax
    # = total when a discount is present (mismatch → Warning — decision 1).
    discounted = discount is not None and discount != _ZERO
    if subtotal is not None and tax is not None and total is not None:
        if discounted:
            computed = subtotal - discount + tax
            diff = abs(computed - total)
            if diff > tolerance:
                add("W_DISCOUNT_EQUATION", SEVERITY_WARNING,
                    f"subtotal − discount + tax = {computed} does not match "
                    f"the stated total {total} (difference {diff}).")
        else:
            diff = abs(subtotal + tax - total)
            if diff > tolerance:
                add("E_AMOUNT_PRIMARY_MISMATCH", SEVERITY_ERROR,
                    f"subtotal + tax = {subtotal + tax} does not match the "
                    f"stated total {total} (difference {diff}).")

    # -- R3: §8.2 line-item sum (sum of line amounts = subtotal) -----------
    amounts = [_decimal(line.get("amount")) for line in lines]
    if subtotal is not None and lines and all(a is not None for a in amounts):
        line_sum = sum(amounts)
        diff = abs(line_sum - subtotal)
        if diff > tolerance:
            add("E_LINE_SUM_MISMATCH", SEVERITY_ERROR,
                f"line-item amounts sum to {line_sum}, which does not match "
                f"the stated subtotal {subtotal} (difference {diff}).")

    # -- R4: §8.3 date validation ------------------------------------------
    invoice_date = _parse_iso(_raw(fields, "invoice_date"))
    due_date = _parse_iso(_raw(fields, "due_date"))
    if invoice_date is not None and invoice_date > today:
        add("E_INVOICE_DATE_FUTURE", SEVERITY_ERROR,
            f"invoice date {invoice_date.isoformat()} is in the future "
            f"(today is {today.isoformat()}).", field="invoice_date")
    if invoice_date is not None and due_date is not None and due_date < invoice_date:
        add("E_DUE_DATE_BEFORE_INVOICE", SEVERITY_ERROR,
            f"due date {due_date.isoformat()} is earlier than the invoice "
            f"date {invoice_date.isoformat()}.", field="due_date")

    # -- R5: §8.4 GSTIN format ---------------------------------------------
    gstin = _raw(fields, "vendor_tax_id")
    if gstin is not None and not _GSTIN_RE.match(gstin.upper()):
        add("W_GSTIN_FORMAT", SEVERITY_WARNING,
            f"tax ID {gstin!r} does not match the expected GSTIN format.",
            field="vendor_tax_id")

    if any(f["severity"] == SEVERITY_ERROR for f in findings):
        verdict = VERDICT_FAILED
    elif any(f["severity"] == SEVERITY_WARNING for f in findings):
        verdict = VERDICT_WARNING
    else:
        verdict = VERDICT_PASSED
    return {"verdict": verdict, "findings": findings}
