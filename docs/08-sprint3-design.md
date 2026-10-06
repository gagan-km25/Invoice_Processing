# 08 — Sprint 3 Design: Review, Edit & Atomic Save

Phase: Sprint 3 planning (approved requirement/exploration/plan docs 01–07;
Sprint 2 complete at commit `0a0f5cb`). Date: 2026-10-06.
Status: **DRAFT — awaiting user approval before implementation.**
Goal: extend the flow from *upload → validate → extract* to
*upload → validate → extract → **review/edit → validate → save** → SQLite*.

---

## 1. User Stories

| ID | Story | Tier |
|---|---|---|
| US-S3-01 | As a user, after uploading an invoice, I want to review extracted invoice information before saving it. | Must |
| US-S3-02 | As a user, I want to edit incorrect extracted fields before saving. | Must |
| US-S3-03 | As a user, I want to edit, add, or remove invoice line items before saving. | Must |
| US-S3-04 | As a user, I want invalid values to be rejected with clear validation messages. | Must |
| US-S3-05 | As a user, I want the corrected invoice to be saved atomically to SQLite. | Must |
| US-S3-06 | As a user, I want duplicate invoices to require confirmation before creating another saved record. | Must |
| US-S3-07 | As a user, I want a clear success message after the invoice is saved. | Must |

No additional major features are introduced. One small affordance is added and
documented here: the home page's recent-invoices table gains a **Review** link
for records in `extracted` state — without it, a user who navigates away from
the post-upload redirect cannot reach the review page at all (US-S3-01 is
unreachable otherwise).

## 2. Acceptance Criteria

### US-S3-01 — Review before saving
- **AC-01.1** Given a successfully extracted upload, the user lands on
  `GET /invoices/<id>/review` showing all 12 header fields and all extracted
  line items pre-filled.
- **AC-01.2** Fields whose draft status is `ambiguous` or `missing` are
  visually flagged on the review page.
- **AC-01.3** No record reaches `status='saved'` without an explicit save
  action on the review page.
- **AC-01.4** Unknown id → 404. Non-`extracted` record (uploaded/failed/saved)
  → redirect to home with an explanatory flash; the review form never renders
  for it.

### US-S3-02 — Edit header fields
- **AC-02.1** Editing any header field and saving persists exactly the
  submitted value (DB equals form, not the extraction).
- **AC-02.2** Untouched fields persist their extracted values.

### US-S3-03 — Edit / add / remove line items
- **AC-03.1** Editing a line's description, quantity, unit price, or amount
  persists the edited values.
- **AC-03.2** A row marked *remove* is absent from `invoice_lines` after save.
- **AC-03.3** Added rows persist with server-assigned sequential
  `line_number` (1..n in submitted order).
- **AC-03.4** Rows left entirely blank are silently ignored (not errors, not
  stored).

### US-S3-04 — Validation
- **AC-04.1** Required fields: `invoice_number`, `invoice_date`, `subtotal`,
  `total`. Blank/whitespace → save blocked with a per-field message.
- **AC-04.2** Decimal fields (subtotal, discount, tax, total, quantity, unit
  price, line amount): must parse as decimal; `1250.5` is accepted and
  quantized to `1250.50`; non-numeric → blocked, field named.
- **AC-04.3** Dates must be `YYYY-MM-DD`; anything else → blocked, format
  named. Optional `due_date` earlier than `invoice_date` → visible **warning**,
  save allowed (E-16 philosophy: flag, don't block).
- **AC-04.4** Quantity must be > 0; unit price ≥ 0; violations → blocked.
- **AC-04.5** Currency, if provided, must be a 3-letter code (stored
  uppercase); otherwise blank.
- **AC-04.6** Line amount deviating from `quantity × unit_price` by > 0.01 →
  visible **warning**, save allowed.
- **AC-04.7** `|subtotal − discount − tax − total| > 0.01` (discount/tax when
  present) → visible **warning**, save allowed (E-16).
- **AC-04.8** Any blocked validation persists nothing: status stays
  `extracted`, `invoice_lines` unchanged, and the review page re-renders with
  a validation summary plus per-field messages.

### US-S3-05 — Atomic save
- **AC-05.1** Save writes header columns and the full line set in **one
  transaction**; a simulated failure mid-transaction leaves the record
  completely unchanged (header *and* prior lines) with an error flash.
- **AC-05.2** Successful save sets `status='saved'`, bumps `updated_at`.
- **AC-05.3** A record not in `extracted` state cannot be saved (guard; e.g.
  double-submit of an already-saved record is rejected, not duplicated).
- **AC-05.4** `extraction_json` is left untouched by save (it remains the
  pre-review audit record).

### US-S3-06 — Duplicate confirmation
- **AC-06.1** Saving when an existing **saved** record matches on
  vendor + invoice number (case-insensitive) → warning naming the prior
  record(s), with an explicit confirmation checkbox; no second record is
  created without it.
- **AC-06.2** Saving a file whose SHA-256 already has a **saved** record →
  same warning + confirmation.
- **AC-06.3** After ticking the confirmation and resubmitting, the save
  proceeds and creates the new record.
- **AC-06.3b** Non-saved records (uploaded/extracted drafts) never trigger the
  duplicate warning.

### US-S3-07 — Success feedback
- **AC-07.1** After a successful save the user sees "Invoice #N saved." and
  the home page lists the record with status `saved`.

## 3. Exploration Findings (current Sprint 2 state, verified)

| Question | Finding |
|---|---|
| 1. Reusable columns | **All** header columns are reusable as-is: vendor, vendor_tax_id, invoice_number, invoice_date, due_date, bill_to, currency, subtotal, discount, tax, tax_rate, total. No changes needed. |
| 2. Columns needing modification | **None.** The Sprint 2 migration already added everything review/save needs. `updated_at` just needs bumping on save. |
| 3. `invoice_lines` sufficiency | Sufficient: line_number, description, quantity REAL, unit_price REAL, amount REAL, FK with CASCADE. Edit/add/remove is handled by the existing replace pattern (DELETE + INSERT inside one transaction — same as `update_extraction` uses). |
| 4. `extraction_json` handling | **Preserved untouched on save** — it is the pre-review audit record ("what the machine read"). The review page reads it to render ambiguity/missing flags; the saved columns hold the human-confirmed values. |
| 5. Status transitions today | `uploaded → extracted` (extraction service) and `→ failed` (error path). `saved` exists in the CHECK constraint but nothing sets it yet — Sprint 3 implements `extracted → saved` with a guard (only from `extracted`). |
| 6. Duplicate detection today | Upload-time only: file-hash, non-blocking flash (FR-15 part 1). The save-time vendor+invoice-number check and confirm-before-create do **not** exist yet — new repository finder + confirmation flow. |
| 7. Review route placement | New `invoices` blueprint (`routes/invoices.py`): `GET /invoices/<id>/review` + `POST /invoices/<id>/save`. The existing upload route only changes its success redirect target. |
| 8. Layering | Preserved: `routes/invoices.py` (HTTP only) → `services/review.py` (form parsing, validation, merge) → `db/repository.py` (transaction). Parser package untouched. |

## 4. Architecture & Design

**Route flow**

```
POST /upload (existing) ──extraction ok──> redirect GET /invoices/<id>/review
        └─extraction failed─> redirect / (error flash, as today)

GET  /invoices/<id>/review   → render review.html (draft values + flags + lines)
POST /invoices/<id>/save     → services/review.validate_and_merge(form)
        ├─ invalid            → re-render review + per-field errors (nothing persisted)
        ├─ duplicate & !confirmed → re-render review + warning banner + confirm checkbox
        └─ ok (or confirmed)  → repository.save_invoice (one transaction)
                                → flash "Invoice #N saved." → redirect /
```

**Review page & form.** One form, plain HTML (no JS required):
- Header inputs for all 12 fields; date fields use `type="date"`
  (`YYYY-MM-DD`); amounts `type="text"` with `inputmode="decimal"` (HTML date/
  number quirks avoided; server validates everything anyway).
- Each field renders its draft flag (`ambiguous`/`missing`) and, after a
  failed validation, its error message inline.
- Line items as rows: `remove` checkbox + description + quantity + unit price
  + amount per row; an "add N blank rows" select provides add-without-JS;
  blank rows are ignored server-side; line numbers re-assigned 1..n on save.
- Duplicate case re-renders the *same* form with a warning banner and a
  `confirm_duplicate` checkbox — state lives in the form, no server-side stash.

**Server-side validation (`services/review.py`).** Pure function
`validate_and_merge(form, draft) -> (data | errors, warnings)`:
- required: invoice_number, invoice_date, subtotal, total (AC-04.1)
- decimals via `parser.normalize.parse_amount` (reuse, not duplication),
  quantized 0.01 (AC-04.2); quantity > 0, unit price ≥ 0 (AC-04.4)
- dates `YYYY-MM-DD`; due < invoice → warning (AC-04.3)
- currency `^[A-Za-z]{3}$` uppercased or blank (AC-04.5)
- line amount vs qty×unit → warning (AC-04.6); subtotal−discount+tax vs total
  → warning (AC-04.7); blank rows dropped (AC-03.4)
- text length caps (≤ 200 chars) on free-text fields

**Transaction boundaries (`repository.save_invoice`).** Single connection,
single transaction: guard `status='extracted'` → UPDATE header (incl.
`status='saved'`, `updated_at`) → DELETE old lines → INSERT submitted lines →
COMMIT; any exception → ROLLBACK + re-raise (AC-05.x). New finder
`find_saved_duplicates(vendor, invoice_number, exclude_id)` (COLLATE NOCASE,
`status='saved'`) alongside existing `find_by_hash`.

**Success/error handling.** Success flash (AC-07.1); blocked validation re-
renders with summary + inline errors; unexpected save exception → flash
"save failed, nothing changed" + record untouched.

**Security.** POSTs only for state changes; **T-G lands here**: a
`before_request` Origin/Host check rejects cross-site POSTs to localhost
(403) — a malicious webpage must not be able to drive-by-save. Jinja
autoescaping everywhere (invoice text is third-party data); parameterized SQL
only; unknown ids → 404; status guard blocks saving/stale double-submits;
input length caps. No new file/paths are touched by this sprint.

**Templates/static.** `review.html` (new); `index.html` gains the Review link
column; `style.css` gains form/table-error styles; `main.js` unchanged
(no-JS-first).

## 5. Files to create / modify

| File | Change |
|---|---|
| `app/routes/invoices.py` | **new** — review + save routes (thin) |
| `app/services/review.py` | **new** — form parsing, validation, merge (pure) |
| `app/templates/review.html` | **new** — review/edit form with flags, lines editor, duplicate banner |
| `app/__init__.py` | register invoices blueprint; Origin/Host check hook (T-G) |
| `app/db/repository.py` | `save_invoice`, `find_saved_duplicates` |
| `app/routes/uploads.py` | success redirect → review page |
| `app/templates/index.html` | Review link for `extracted` rows |
| `app/static/css/style.css` | form, error, banner styles |
| `tests/unit/test_review_validation.py` | **new** — validation rules |
| `tests/integration/test_review_save_flow.py` | **new** — HTTP flows incl. duplicates, rollback, Origin check |
| `tests/integration/test_extraction_flow.py` | update redirect-target expectations (documented) |
| `docs/04` / `docs/06` / `CHANGELOG.md` | results/log/release notes at sprint end |

## 6. Test strategy

- **Unit — review validation** (bulk): required fields; decimal parse/quantize/
  rejections; date format + due<invoice warning; currency rules; quantity>0 /
  unit≥0; blank-row dropping; line amount and totals consistency warnings;
  merge output correctness. Pure functions — no Flask needed.
- **Unit — repository**: save_invoice happy path (header + lines in one
  transaction, status/updated_at); status guard (non-extracted → error, no
  change); **rollback test** — injected failure on the line INSERT must leave
  header AND prior lines untouched.
- **Integration (HTTP, temp DB)**: full happy path upload→review→save with a
  correction (DB equals submitted values); validation failure persists
  nothing and re-renders messages; duplicate warn → no record → confirm →
  saved; hash-duplicate path; unknown id 404; non-extracted review → redirect;
  Origin check 403; Review link on index; double-submit guard.
- **Regression**: entire existing suite stays green; the only prior-test
  edits are the documented redirect-target expectation updates.

## 7. Risks & mitigations

| # | Risk | Mitigation |
|---|---|---|
| R-S3-1 | Line-row form parsing is fiddly (indexed names, blank-row semantics) | Deterministic indexed field names; pure form-parsing function under unit test |
| R-S3-2 | Redirect change breaks Sprint 1/2 tests | Update expectations transparently, keep assertions meaningful; full-suite gate before commit |
| R-S3-3 | Double-submit creates confusion or duplicate saves | Status guard: only `extracted` → `saved`; second submit rejected cleanly |
| R-S3-4 | Validation re-implements parser logic differently | Reuse `normalize.parse_amount`/date rules — one source of truth |
| R-S3-5 | Scope creep (detail pages, edit-after-save, delete) | Explicit exclusions below; those are Sprint 4 stories |
| R-S3-6 | Duplicate confirmation state lost on re-render | State stays in the form (checkbox); no server stash to lose |

## 8. Scope exclusions (confirmed)

Not in Sprint 3: invoice history/search, detail management pages, delete,
edit-after-save, dashboards, OCR, authentication, deployment, unrelated UI
redesign. (Per prompt + approved plan: list/search/sort, detail, edit, delete
belong to Sprint 4.)

## 9. Definition of Done (Sprint 3)

All ACs above pass (automated); full suite green; test results recorded in
docs/04; dev log + prompt log updated; CHANGELOG entry; single commit after
user-visible verification of the review→save flow.

## 10. Implementation amendments (recorded post-implementation)

Three small deviations discovered during implementation, all within the
approved intent:
1. **Warnings on the success path** — "visible warning" (AC-04.3/04.6/04.7) is
   implemented as flash messages on the post-save redirect as well as on the
   re-render path, so a mismatch is never silently swallowed.
2. **Loopback Origin equivalence** — the T-G check treats
   localhost/127.0.0.1/::1 as equivalent hosts (browsers may send either for
   the same localhost server); everything else with an Origin is 403.
3. **Blank add-rows always present** — the review form always renders three
   empty rows below the extracted lines (add-items without JavaScript);
   fully blank rows are ignored on save (AC-03.4).
