"""Sprint E3 unit tests — business validation engine (assignment §8).

Pure-function tests: no DB, no Flask (architecture rule). `today` is
injected for determinism (approved decision 3); tolerance is passed
explicitly so boundary semantics are pinned regardless of app config.
"""
from datetime import date
from decimal import Decimal

from app.services.validation import (
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    VERDICT_FAILED,
    VERDICT_PASSED,
    VERDICT_WARNING,
    validate,
)

TODAY = date(2026, 10, 13)
TOL = Decimal("0.01")


def _fields(**overrides):
    """Draft header with every §8.1 mandatory field present and consistent
    (100.00 + 8.00 = 108.00)."""
    base = {
        "invoice_number": {"status": "found", "value": "INV-001"},
        "invoice_date": {"status": "found", "value": "2026-09-30"},
        "vendor": {"status": "found", "value": "Acme Corporation"},
        "currency": {"status": "found", "value": "USD"},
        "subtotal": {"status": "found", "value": "100.00"},
        "tax": {"status": "found", "value": "8.00"},
        "total": {"status": "found", "value": "108.00"},
    }
    base.update(overrides)
    return base


def _codes(result):
    return [finding["code"] for finding in result["findings"]]


def _f(value):
    return {"status": "found", "value": value}


def _line(amount, description="Widget"):
    return {"description": description, "quantity": "1",
            "unit_price": amount, "amount": amount}


# ------------------------------------------------------------ R1: mandatory

def test_clean_invoice_passes():
    """All mandatory fields present, equations consistent → passed, no findings."""
    result = validate(_fields(), [], today=TODAY, tolerance=TOL)
    assert result["verdict"] == VERDICT_PASSED
    assert result["findings"] == []


def test_each_missing_mandatory_field_is_an_error():
    """Removing any one §8.1 field yields exactly its E_MISSING_* error."""
    for name, code in (
        ("invoice_number", "E_MISSING_INVOICE_NUMBER"),
        ("invoice_date", "E_MISSING_INVOICE_DATE"),
        ("vendor", "E_MISSING_VENDOR"),
        ("currency", "E_MISSING_CURRENCY"),
        ("total", "E_MISSING_TOTAL"),
    ):
        fields = _fields()
        fields.pop(name)
        result = validate(fields, [], today=TODAY, tolerance=TOL)
        assert _codes(result) == [code], name
        assert result["verdict"] == VERDICT_FAILED
        assert result["findings"][0]["severity"] == SEVERITY_ERROR
        assert result["findings"][0]["field"] == name


def test_all_mandatory_missing_reports_all_five():
    """Every missing §8.1 field is reported — not just the first."""
    result = validate({}, [], today=TODAY, tolerance=TOL)
    assert len(result["findings"]) == 5
    assert result["verdict"] == VERDICT_FAILED


def test_blank_value_counts_as_missing():
    """A found-but-empty string is treated as missing (E3 planning rule)."""
    result = validate(_fields(total={"status": "found", "value": ""}),
                      [], today=TODAY, tolerance=TOL)
    assert "E_MISSING_TOTAL" in _codes(result)


def test_ambiguous_value_counts_as_present():
    """An ambiguous extraction still carries a value — validation uses it."""
    result = validate(_fields(total={"status": "ambiguous", "value": "108.00"}),
                      [], today=TODAY, tolerance=TOL)
    assert result["verdict"] == VERDICT_PASSED


def test_missing_status_treated_as_absent():
    """status='missing' means the value is ignored even if present."""
    result = validate(_fields(total={"status": "missing", "value": "108.00"}),
                      [], today=TODAY, tolerance=TOL)
    assert "E_MISSING_TOTAL" in _codes(result)


# ------------------------------------------------- R2: primary amount rule

def test_primary_equation_mismatch_is_error():
    """subtotal + tax ≠ total beyond tolerance → error (approved decision 1)."""
    result = validate(_fields(total={"status": "found", "value": "110.00"}),
                      [], today=TODAY, tolerance=TOL)
    assert _codes(result) == ["E_AMOUNT_PRIMARY_MISMATCH"]
    assert result["verdict"] == VERDICT_FAILED


def test_primary_equation_exactly_at_tolerance_passes():
    """Inclusive boundary: |diff| == 0.01 passes (approved E3 correction)."""
    result = validate(_fields(total={"status": "found", "value": "108.01"}),
                      [], today=TODAY, tolerance=TOL)
    assert result["verdict"] == VERDICT_PASSED


def test_primary_equation_just_above_tolerance_fails():
    """0.011 difference fails: no premature quantization (approved E3
    precision correction — quantizing 0.011 → 0.01 would wrongly pass)."""
    result = validate(_fields(total={"status": "found", "value": "108.011"}),
                      [], today=TODAY, tolerance=TOL)
    assert _codes(result) == ["E_AMOUNT_PRIMARY_MISMATCH"]


def test_missing_tax_skips_primary_rule():
    """The primary equation needs subtotal, tax AND total; a missing tax
    must not crash or fabricate a mismatch (tax is not §8.1-mandatory)."""
    fields = _fields()
    fields.pop("tax")
    result = validate(fields, [], today=TODAY, tolerance=TOL)
    assert result["verdict"] == VERDICT_PASSED


def test_non_numeric_amount_does_not_crash():
    """A non-numeric value degrades to None — the amount rules skip it."""
    result = validate(_fields(total={"status": "found", "value": "lots"}),
                      [], today=TODAY, tolerance=TOL)
    assert "E_AMOUNT_PRIMARY_MISMATCH" not in _codes(result)


# ----------------------------------------------------- R3: line-item sums

def test_matching_line_sum_passes():
    """Overriding subtotal requires a consistent tax/total pair — the
    primary equation always applies alongside the line-sum rule."""
    fields = _fields(subtotal=_f("30.00"), tax=_f("0.00"), total=_f("30.00"))
    result = validate(fields, [_line("10.00"), _line("20.00")],
                      today=TODAY, tolerance=TOL)
    assert result["verdict"] == VERDICT_PASSED


def test_line_sum_mismatch_is_error():
    """Line amounts summing beyond tolerance from subtotal → error
    (approved E3 planning correction: Error, not Warning)."""
    fields = _fields(subtotal=_f("30.00"), tax=_f("0.00"), total=_f("30.00"))
    result = validate(fields, [_line("10.00"), _line("25.00")],
                      today=TODAY, tolerance=TOL)
    assert _codes(result) == ["E_LINE_SUM_MISMATCH"]
    assert result["verdict"] == VERDICT_FAILED


def test_line_sum_exactly_at_tolerance_passes():
    fields = _fields(subtotal=_f("30.01"), tax=_f("0.00"), total=_f("30.01"))
    result = validate(fields, [_line("10.00"), _line("20.00")],
                      today=TODAY, tolerance=TOL)
    assert "E_LINE_SUM_MISMATCH" not in _codes(result)
    assert result["verdict"] == VERDICT_PASSED


def test_no_lines_skips_line_sum_rule():
    """No line items → the line-sum rule cannot apply (nothing to sum)."""
    result = validate(_fields(), [], today=TODAY, tolerance=TOL)
    assert "E_LINE_SUM_MISMATCH" not in _codes(result)


def test_line_with_unparseable_amount_skips_line_sum_rule():
    """A None line amount makes the sum indeterminable → rule skipped."""
    lines = [_line("10.00"), {"description": "X", "quantity": "1",
                              "unit_price": "5", "amount": None}]
    result = validate(_fields(subtotal={"status": "found", "value": "30.00"}),
                      lines, today=TODAY, tolerance=TOL)
    assert "E_LINE_SUM_MISMATCH" not in _codes(result)


# ------------------------------------------------------------- R4: dates

def test_future_invoice_date_is_error():
    """Invoice date after today → error (approved E3 correction from the
    original warning)."""
    result = validate(_fields(invoice_date={"status": "found",
                                            "value": "2026-10-14"}),
                      [], today=TODAY, tolerance=TOL)
    assert _codes(result) == ["E_INVOICE_DATE_FUTURE"]
    assert result["verdict"] == VERDICT_FAILED


def test_invoice_date_today_passes():
    result = validate(_fields(invoice_date={"status": "found",
                                            "value": "2026-10-13"}),
                      [], today=TODAY, tolerance=TOL)
    assert result["verdict"] == VERDICT_PASSED


def test_due_before_invoice_is_error():
    """due date earlier than invoice date → error (approved E3 correction)."""
    result = validate(_fields(due_date={"status": "found", "value": "2026-09-29"}),
                      [], today=TODAY, tolerance=TOL)
    assert _codes(result) == ["E_DUE_DATE_BEFORE_INVOICE"]
    assert result["verdict"] == VERDICT_FAILED


def test_due_equal_invoice_passes():
    result = validate(_fields(due_date={"status": "found", "value": "2026-09-30"}),
                      [], today=TODAY, tolerance=TOL)
    assert result["verdict"] == VERDICT_PASSED


def test_unparseable_date_is_ignored_by_date_rules():
    """A non-ISO date can't be compared — the date rules skip (the mandatory
    and format layers elsewhere own format complaints)."""
    result = validate(_fields(invoice_date={"status": "found", "value": "15/01/2026"}),
                      [], today=TODAY, tolerance=TOL)
    assert "E_INVOICE_DATE_FUTURE" not in _codes(result)


def test_today_default_is_local_date():
    """Without injection, today defaults to the local date — a past invoice
    date still passes (decision 3: injectable for tests, local for runtime)."""
    result = validate(_fields(), [])
    assert result["verdict"] == VERDICT_PASSED


# -------------------------------------------------------------- R5: GSTIN

def test_valid_gstin_no_finding():
    gstin = {"status": "found", "value": "22AAAAA0000A1Z5"}
    result = validate(_fields(vendor_tax_id=gstin), [], today=TODAY, tolerance=TOL)
    assert result["verdict"] == VERDICT_PASSED


def test_invalid_gstin_warns_not_fails():
    """Present-but-malformed GSTIN → warning (approved decision 1)."""
    gstin = {"status": "found", "value": "NOT-A-GSTIN"}
    result = validate(_fields(vendor_tax_id=gstin), [], today=TODAY, tolerance=TOL)
    assert _codes(result) == ["W_GSTIN_FORMAT"]
    assert result["findings"][0]["severity"] == SEVERITY_WARNING
    assert result["verdict"] == VERDICT_WARNING  # warnings never block


def test_absent_gstin_no_finding():
    """GSTIN is optional — absent means silent (no false warning)."""
    result = validate(_fields(), [], today=TODAY, tolerance=TOL)
    assert "W_GSTIN_FORMAT" not in _codes(result)


# ------------------------------------------------- R6: discount equation

def test_zero_discount_skips_discount_rule():
    result = validate(_fields(discount={"status": "found", "value": "0.00"}),
                      [], today=TODAY, tolerance=TOL)
    assert "W_DISCOUNT_EQUATION" not in _codes(result)


def test_absent_discount_skips_discount_rule():
    result = validate(_fields(), [], today=TODAY, tolerance=TOL)
    assert "W_DISCOUNT_EQUATION" not in _codes(result)


def test_discounted_total_consistent_passes():
    """A correctly discounted invoice (100 − 10 + 8 = 98) passes cleanly:
    the discount-aware equation governs discounted invoices — the literal
    subtotal + tax check would reject every valid discounted invoice
    (the assignment's own discounted evaluation samples state
    subtotal − discount + tax = total)."""
    fields = _fields(discount=_f("10.00"), total=_f("98.00"))
    result = validate(fields, [], today=TODAY, tolerance=TOL)
    assert result["verdict"] == VERDICT_PASSED
    assert result["findings"] == []


def test_discount_equation_mismatch_warns():
    """discount ≠ 0 and subtotal − discount + tax ≠ total → warning only
    (approved decision 1 + 4): the discount-aware mismatch never blocks."""
    fields = _fields(discount=_f("10.00"))
    # discount-aware: 100 − 10 + 8 = 98 ≠ 108
    result = validate(fields, [], today=TODAY, tolerance=TOL)
    assert _codes(result) == ["W_DISCOUNT_EQUATION"]
    assert result["verdict"] == VERDICT_WARNING


def test_error_dominates_warning_in_verdict():
    """Any error → failed even when warnings are also present."""
    fields = _fields(discount={"status": "found", "value": "10.00"},
                     vendor_tax_id={"status": "found", "value": "BAD"})
    fields.pop("currency")
    result = validate(fields, [], today=TODAY, tolerance=TOL)
    assert set(_codes(result)) >= {"E_MISSING_CURRENCY", "W_GSTIN_FORMAT",
                                   "W_DISCOUNT_EQUATION"}
    assert result["verdict"] == VERDICT_FAILED


# ---------------------------------------------------------- precision misc

def test_decimal_and_string_inputs_equivalent():
    """Values may arrive as Decimal (parser) or str (JSON) — same verdict."""
    decimal_fields = _fields(total={"status": "found",
                                    "value": Decimal("108.00")})
    assert validate(decimal_fields, [], today=TODAY, tolerance=TOL)["verdict"] == \
        validate(_fields(), [], today=TODAY, tolerance=TOL)["verdict"]


def test_zero_tolerance_is_strict():
    """tolerance=0: any nonzero difference fails — tolerance is honored,
    not hard-coded."""
    result = validate(_fields(total={"status": "found", "value": "108.005"}),
                      [], today=TODAY, tolerance=Decimal("0"))
    assert _codes(result) == ["E_AMOUNT_PRIMARY_MISMATCH"]


def test_findings_carry_message_and_severity():
    """Finding shape contract: code, severity, message (and optional field)."""
    result = validate({}, [], today=TODAY, tolerance=TOL)
    finding = result["findings"][0]
    assert set(finding) >= {"code", "severity", "message"}
