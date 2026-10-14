# DECISION RECORD — Sprint E3 amount validation with discounts

| | |
|---|---|
| **Decision ID** | D-E3-01 |
| **Date** | 2026-10-13 |
| **Status** | **Approved** — user ruling during the Sprint E3 acceptance review |
| **Scope** | Severity and applicability of the assignment §8.2 amount-equation checks when an invoice carries a discount |
| **Supersedes** | The literal two-check reading of the E3 planning decisions (those decisions were recorded in conversation only; `docs/05-prompt-log.md` ends at the Sprint E1 commit, P-E-33) |
| **Effect on code** | **None** — the implementation already matched this ruling; no application code or test was changed by this record |

---

## 1. The assignment's exact requirement

Assignment §8.2 ("Amount Validation"), verbatim:

```text
Subtotal + Tax Amount = Total Amount
```

Also validate:

```text
Sum of Line Item Totals = Subtotal
```

A small configurable tolerance may be allowed for rounding differences
(example: ₹0.01).

The word "discount" does not appear anywhere in the assignment. §8.5
defines three verdicts — `Passed`, `Warning`, `Failed` — and requires only
that "the user should be able to understand why a validation failed or
generated a warning"; it assigns no severity to any specific check.

## 2. The five supplied invoices (docs/07, Phase-A verified)

`docs/07-invoice-exploration.md` transcribes the five supplied sample
invoices (lines 28–35) **before any parser code existed**:

| # | Sample | Subtotal | Discount | Tax | Grand Total |
|---|---|---|---|---|---|
| 1 | retail | 6,550.00 | 0.00 | 1,179.00 | 7,729.00 |
| 2 | services | 31,500.00 | 500.00 | 5,580.00 | 36,580.00 |
| 3 | | 14,045.00 | 750.00 | 1,595.40 | 14,890.40 |
| 4 | | 15,600.00 | 300.00 | 765.00 | 16,065.00 |
| 5 | | 52,100.00 | 1,250.00 | 9,153.00 | 60,003.00 |

Applying both candidate equations (Decimal, exact):

| # | `subtotal + tax` (literal §8.2) | `subtotal − discount + tax` | Grand Total |
|---|---|---|---|
| 1 | 7,729.00 → **PASS** | 7,729.00 → pass | 7,729.00 |
| 2 | 37,080.00 → **FAIL** (by exactly 500.00) | 36,580.00 → **PASS** | 36,580.00 |
| 3 | 15,640.40 → **FAIL** (by exactly 750.00) | 14,890.40 → **PASS** | 14,890.40 |
| 4 | 16,365.00 → **FAIL** (by exactly 300.00) | 16,065.00 → **PASS** | 16,065.00 |
| 5 | 61,253.00 → **FAIL** (by exactly 1,250.00) | 60,003.00 → **PASS** | 60,003.00 |

Four of the five supplied invoices fail the literal equation **by exactly
the discount amount**; all five satisfy the discount-aware equation
exactly. These invoices are correctly issued documents — docs/07 finding 5
records the consequence: "consistency math is `subtotal − discount + tax =
total` (verified exact on all five; also `tax = (subtotal − discount) ×
rate`)" — i.e. the tax itself is computed on the discounted subtotal, so
the discount-aware form reflects how the invoices are actually constructed.
The docs/07 validation plan (lines 119–121) likewise specifies
"`subtotal − discount + tax ≈ total` (or without discount when absent)",
as a flagged check, never blocking.

## 3. Prior approved art

- **Sprint 3, AC-04.7** (docs/08-sprint3-design.md, implemented in the
  committed baseline's `review.py` `_consistency_warnings`):
  discount-aware consistency deviating > 0.01 → visible **warning**, save
  allowed (E-16 "flag, don't block"). (docs/08 line 71 contains a sign
  typo `subtotal − discount − tax − total`; the implemented and approved
  computation is `subtotal − discount + tax`.)
- **E3 planning decisions** (approved in conversation): decision 1 —
  primary-equation mismatch → Error, discount-aware mismatch → Warning,
  warnings never block; decision 4 — "preserve the previously approved
  rules", which for discount handling is exactly AC-04.7.

## 4. Approved rule (Interpretation A — applicable-equation model)

For each extracted invoice, exactly one amount equation applies:

1. **Discount absent or zero** → validate `subtotal + tax = total`.
   A mismatch beyond tolerance is an **Error** (verdict `failed`).
2. **Discount nonzero** → validate `subtotal − discount + tax = total`.
   A mismatch beyond tolerance is a **Warning** (verdict `warning`);
   processing is never blocked (E-16).
3. In both cases: line-item amounts must sum to the subtotal within
   tolerance; a mismatch is an **Error** (§8.2 second equation).
4. All comparisons use **Decimal arithmetic**, values as produced by
   parsing/coercion (2dp), differences computed at full precision and
   compared against the **configured, inclusive tolerance**
   (`VALIDATION_TOLERANCE`, default `Decimal("0.01")`; `diff ≤ tolerance`
   passes). No intermediate quantization (a ₹0.011 difference fails a
   ₹0.01 tolerance).

An unparseable discount is treated as absent (rule 1) — the record then
carries the data-quality signal through the amount checks.

## 5. Why the implementation is retained

`app/services/validation.py` (R2/R6 block) already implements exactly
rule 1–4 above, and it is the only reading consistent with every written
source:

- The literal two-check alternative (plain equation always an Error plus a
  separate discount-aware warning) fails 4 of the 5 supplied invoices —
  contradicting docs/07's "verified exact on all five" and the purpose of
  the supplied corpus.
- It preserves both approved severities of planning decision 1 (Error for
  the no-discount equation, Warning for the discount-aware equation).
- It honours planning decision 4's "preserve the previously approved
  rules" clause — the previously approved rule (Sprint 3 AC-04.7) is the
  discount-aware equation at warning severity.

Residual behaviour accepted with this ruling: a grossly wrong total on a
discounted invoice is "only" a warning — surfaced on the detail page and
review warnings, and gated later by human review/approval (Sprint 3 E-16
philosophy). Any stricter calibration (e.g. an Error threshold for large
discount-aware deviations) would be a **new** decision, not covered by
this record.

## 6. Effects of this ruling

- `docs/USER_STORIES.md` US-E3-1 acceptance criterion 2 now documents both
  equation forms and their severities.
- All five supplied invoices validate `passed` end-to-end
  (TC-S2-E01…E05, `tests/integration/test_extraction_flow.py`).
- No application code and no tests were altered by this record; the full
  suite is green as reported in the Sprint E3 completion report and
  re-verified in `docs/TEST_PLAN.md`.
