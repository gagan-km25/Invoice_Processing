# 07 — Sprint 2: Real-Invoice Exploration, Parser Design & Implementation Plan

Phase: Sprint 2 (extraction & parser). Date: 2026-10-06.
Inputs: five real samples in `sample_invoices/` (git-ignored, never modified),
inspected with pdfplumber 0.11.10 (two-view approach per approved design).

---

## Phase A — Exploration findings (actual, per invoice)

All five are single-page PDFs sharing one layout family ("TAX INVOICE" header,
two-column top block, one line-item table that *also contains the totals rows*,
8-pt footer). Text extraction is clean; **table extraction is reliable**;
word coordinates are available and correct; no values were found split across
lines. The layouts are similar enough for one strategy, with the variations
noted below — but the parser is still built layout-tolerant (label + table +
geometric fallbacks) because only five samples exist.

| Finding | 001_retail | 002_services | 003_multiitem | 004_alternate | 005_complex |
|---|---|---|---|---|---|
| Pages | 1 | 1 | 1 | 1 | 1 |
| Vendor | TechNova Retail Pvt. Ltd. | BrightEdge Consulting | Metro Office Supplies | GreenLeaf Foods & Beverages | CloudPeak Systems India Pvt. Ltd. |
| Vendor address | 42 MG Road, Bengaluru, Karnataka 560001 | 18 Residency Road, Bengaluru, Karnataka 560025 | 77 Commercial Street, Bengaluru, Karnataka 560001 | 12 Indiranagar 100 Feet Road, Bengaluru 560038 | 5 Outer Ring Road, Marathahalli, Bengaluru 560037 |
| GST/tax id | GSTIN 29AABCT1234F1Z5 | GSTIN 29AAFCB5678G1Z2 | GSTIN 29AAMO7890H1Z7 | GSTIN 29AAGFG4567J1Z9 | GSTIN 29AACC9012K1Z4 |
| Invoice No | TN-2026-1001 | BEC-SVC-2617 | MOS-88421 | GLF/26/4078 (slashes) | CPS-INV-2026-552 |
| Invoice date | 06-Oct-2026 | 05-Oct-2026 | 04-Oct-2026 | 03-Oct-2026 | 01-Oct-2026 |
| Due date | **absent** — "Payment: Due on receipt" | absent | absent | absent | absent |
| Bill To | Gagan K M | Nagarjuna College of Engineering | Apex Solutions India Pvt. Ltd. | Cityview Hotel | Vertex Digital Labs |
| Line items | 3 | 3 | 8 | 4 | 5 |
| Subtotal | 6,550.00 | 31,500.00 | 14,045.00 | 15,600.00 | 52,100.00 |
| Discount | 0.00 | 500.00 | 750.00 | 300.00 | 1,250.00 |
| Tax label / rate | GST (18%) | GST (18%) | GST (12%) | GST (5%) | GST (18%) |
| Tax amount | 1,179.00 | 5,580.00 | 1,595.40 | 765.00 | 9,153.00 |
| Grand Total | 7,729.00 | 36,580.00 | 14,890.40 | 16,065.00 | 60,003.00 |
| Currency | ₹ rendered as **"n"** | "n" | "n" | "n" | "n" |

**Cross-cutting findings that drive the design:**

1. **Currency glyph corruption.** The rupee sign (₹, U+20B9) is not mapped in
   the embedded font; every amount extracts as `n1,250.00` — a stray letter
   glued to the number. An unmapped-symbol currency *cannot* be read as a
   symbol. However GSTIN + "GST (18%)" are unambiguous India indicators.
2. **Date format is DD-Mon-YYYY** (`06-Oct-2026`) — not the US default assumed
   in requirements. The normalizer needs `%d-%b-%Y` and friends.
3. **No due date exists.** "Payment: Due on receipt" must *not* be parsed as a
   due date (label "Payment:" is not a due-date label; "Due on" must not be
   matched by "Payment Due" patterns).
4. **Totals live inside the item table.** `extract_tables()` merges summary
   rows (`Subtotal`, `Discount`, `GST (18%)`, `Grand Total` — 2-cell rows)
   with item rows (5-cell rows). The parser must separate them.
5. **Discount and tax-rate fields exist and matter.** Schema has no `discount`
   or tax-id column; consistency math is `subtotal − discount + tax = total`
   (verified exact on all five; also `tax = (subtotal − discount) × rate`).
6. **Vendor line shares the text line with "Invoice No:"** — plain-text line
   parsing alone would mis-assign; the reliable vendor source is the first
   table's multi-line cell (`vendor\naddress\nGSTIN: …`), with a geometric
   fallback (leftmost words on the top body-font line).
7. Invoice numbers may contain `/` (GLF/26/4078) — token regex must allow it.
8. Footer (8-pt) says invoices are fictional test data — boilerplate to exclude
   from vendor detection.

## Phase B — Parser design (from the findings)

**Normalized data model** (what `parse()` returns):

```
Draft = {
  fields: {  # every field: {status: found|ambiguous|missing, value, raw?, evidence?}
    vendor, vendor_tax_id, invoice_number, invoice_date, due_date,
    bill_to, currency, subtotal, discount, tax_rate, tax, total
  },
  vendor_address: str|None,          # kept in extraction_json (not a column)
  lines: [{line_number, description, quantity, unit_price, amount}],
  checks: [{rule, passed, detail}],  # Decimal consistency checks
  meta: {page_count, parser_version}
}
```

Schema gains three columns (discovered requirement): `discount REAL`,
`vendor_tax_id TEXT`, `bill_to TEXT` — with an idempotent in-boot migration
(`PRAGMA table_info` → `ALTER TABLE ADD COLUMN`) because Sprint 0 DBs exist.

**Normalization rules** (`normalize.py`, all pure, Decimal at boundaries):
- *Whitespace*: collapse runs, strip, join wrapped lines for label search.
- *Dates*: `DD-Mon-YYYY` (found here), `DD-Mon-YY`, ISO, `Mon D, YYYY`,
  `D Mon YYYY`, `MM/DD/YYYY` (US default; **flagged ambiguous** when the
  alternative reading is also valid, swapped only when day>12 proves D/M).
  Output ISO `YYYY-MM-DD`; unparseable → missing.
- *Amounts*: strip attached symbols/letters (`n1,250.00` → `1,250.00`), drop
  thousands separators (last `,`/`.` before final 2 digits is the decimal
  point — handles `1,234.56` and `1.234,56`), parentheses = negative.
  Always `Decimal`, quantized to 0.01 at the boundary.
- *Currency*: explicit ISO code > known symbol (`$ € £ ₹ ¥`) > **attached
  unknown glyph** (record raw, e.g. `n`) → contextual evidence: GSTIN/GST
  present ⇒ `INR` with `status=ambiguous` + evidence string (never silently
  `found`). Nothing at all ⇒ missing.
- *Invoice numbers*: uppercase token `[A-Z0-9][A-Z0-9/-]{2,}` after the label.

**Field strategies** (`fields.py`), each returning a Field with status:
- *vendor / address / tax-id*: primary = first table's first cell lines
  (`vendor\naddress\nGSTIN:…`); fallback = geometric (leftmost words on the
  top body-font text line, excluding 18-pt title & 8-pt footer & label lines).
- *invoice_number / invoice_date / due_date*: label dictionary + same-line
  value (`Invoice No: X`, `Invoice Date: X`). Due-date labels exclude
  "Payment:" so "Due on receipt" never parses as a date.
- *bill_to*: text after `Bill To:` until the item-table header line.
- *totals (subtotal/discount/tax/total)*: line-based `^Label … amount$` with
  preference orders; tax captures `(rate%)` from the label (`GST (18%)`);
  `Grand Total` preferred over generic `Total`.
- *line items* (`lines.py`): table route — locate the table whose header has
  Description+Qty+Unit Price+Amount; rows with integer leading cell are items;
  2-cell summary rows are surfaced as summary candidates, never items. No
  recognizable table ⇒ zero lines, no error (AC-2.3).

**Status model** (FR-6): `found` / `ambiguous` / `missing` per field, plus
`raw`/`evidence` where inference was involved. Rules: never guess a `found`;
ambiguity is pre-filled but flagged; missing is empty.

**Validation / consistency checks** (Decimal, ±0.01): `subtotal − discount +
tax ≈ total` (or without discount when absent); `due ≥ invoice` when both
present; flagged in `checks`, save never blocked at parser level.

**Layout discrimination**: strategy order is *table-structure first, text
labels second, geometry third* — the exploration showed tables are reliable on
this layout family, while text alone mixes columns; other layouts fall back
gracefully.

**Error containment**: every field strategy runs inside a per-field guard — an
exception marks that field `missing` (with note) instead of aborting; the
service layer additionally wraps the whole parse so any unexpected failure
becomes `status='failed'` + readable message, never a crash (NFR-4).

**OCR**: not needed — text layer is clean on all five real samples. Tesseract
stays out (per instruction and T-I).

## Phase C — Implementation plan

| File | Responsibility |
|---|---|
| `app/services/parser/normalize.py` | text/date/amount/currency/number normalization (pure) |
| `app/services/parser/labels.py` | label dictionaries + preference orders |
| `app/services/parser/fields.py` | per-field strategies → Field dicts |
| `app/services/parser/lines.py` | item/summary table separation, line parsing |
| `app/services/parser/__init__.py` | `parse(text, tables, page_count)` → Draft; per-field guards |
| `app/services/extraction.py` | load record → pdfplumber two-view → parse → persist columns + `extraction_json`, status `extracted`/`failed` |
| `app/db/schema.sql` + `app/db/__init__.py` | 3 new columns + idempotent migration |
| `app/db/repository.py` | `update_extraction()` |
| `routes/uploads.py` | run extraction after store; flash per-outcome |
| `tests/unit/parser/*`, `tests/integration/test_extraction_flow.py` | normalizer cases; field strategies; lines; robustness; 5 real invoices with exact expected values (skip if samples absent) |

**Acceptance criteria:** every asserted field matches the exploration table
exactly on all five invoices; lines match cell-for-cell; consistency checks
pass; garbage input never raises; full suite green; status lifecycle
`uploaded → extracted` observable over HTTP.

**Risks:** currency glyph variant on other machines (mitigation: raw kept +
ambiguous status, evidence-based INR); unseen layouts break table route
(mitigation: text + geometric fallbacks, missing-not-wrong); REAL round-trip
precision (mitigation: Decimal quantize at boundaries, approx asserts 0.001).
