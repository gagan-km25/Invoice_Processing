# Changelog

## [Enhancement — Sprint E0] — 2026-10-12 (branch `enhancement/assignment`)

Invoice Processing System enhancement assignment begins. Baseline:
v1.0.0 (`f69a193`).

- **Added:** versioned schema migration v1→v2 (`app/db/migrations.py`;
  `PRAGMA user_version`): table rebuild preserving IDs, values, timestamps,
  line items; legacy status mapping (`extracted`/`saved` → `completed`,
  original kept in `legacy_status`); one `record_migrated` audit row per
  invoice; `foreign_key_check` gate. Copied-database rehearsal against the
  real `data/invoices.db` PASS; the live database itself was not migrated.
- **Added:** schema v2 (`app/db/schema.sql`): 8-state invoice lifecycle,
  approval/validation/duplicate/AI columns, `invoice_lines.line_tax`,
  `invoice_audit` table, v2 indexes. Status CHECK is transitional (v1
  aliases retained until Sprint E5).
- **Added:** `app/services/workflow.py` — the single status-transition
  authority (legal/illegal transitions incl. terminal `approved`/`rejected`)
  and the §10 approval-routing rule (< ₹1,00,000 → manager, ≥ → finance).
- **Added:** `app/services/audit.py` event catalogue;
  `repository.insert_audit`/`get_audit`/`transition_status` (status + audit
  in one transaction).
- **Added:** env-based AI configuration (Z.ai GLM; key via `ZAI_API_KEY`
  only), `.env.example` placeholders, `.env` git-ignored.
- **Added:** canonical enhancement docs — `docs/REQUIREMENTS.md`,
  `USER_STORIES.md`, `SPRINT_PLAN.md`, `ARCHITECTURE.md`, `TEST_PLAN.md`,
  `KNOWN_ISSUES.md`, root `CLAUDE_USAGE.md` (genuine-evidence rule).
- **Tests:** +51 (migration preservation/idempotency, transitions,
  threshold boundaries, config safeguards). Full suite: 220 passed
  (169 legacy + 51 new).

## [1.0.0] — Invoice Extractor v1 (2026-10-06)

All notable changes to the Invoice Extractor and its enhancement are
documented here. The v1 project followed the sprint plan in
[docs/03-plan.md](03-plan.md); the enhancement follows
[docs/SPRINT_PLAN.md](SPRINT_PLAN.md).

## 1.0.0 — Sprint 6: Final Verification, Documentation & Evaluation Readiness (2026-10-06)

Final release. All planned sprints complete; feature freeze in force.

- Final verification at HEAD: full suite **169 passed / 0 failed / 0 skipped**;
  five real invoices **65/65 field checks** and 23/23 line items; HTTP
  lifecycle re-verified end to end (upload → extract → review → save →
  history → search → detail → original → delete cycle).
- NFR-9 re-verified: clean virtual environment → `pip install -r
  requirements.txt` → full suite + boot, all green.
- Security re-verified: Origin 403, GET-delete 405, injection-safe search,
  contained file serving, invoice isolation.
- Requirements traceability matrix completed (docs/11): every Must/Should
  requirement mapped to stories, criteria, implementation, tests, and
  evidence — with deferred items (edit-after-save, date-range filter/sort,
  OCR, CSV export) marked **honestly as deferred/not selected**, not hidden.
- Documentation finalized: retrospective (docs/12), evaluation Q&A (docs/13),
  README accuracy pass, consolidated final verification record (docs/11).
- Known deferred items (documented, intentional): edit-after-save (FR-11),
  date-range filter + user-selected sort (FR-13 partial), OCR (FR-17),
  CSV export (FR-18).


## 0.6.0 — Sprint 5: Hardening, Edge Cases & OCR Gate (2026-10-06)

- No-text-layer gate: a PDF that opens but contains no selectable text now
  fails with the specific "likely a scan" message (and a `failed` record)
  instead of silently producing an all-missing extraction (AC-7.1).
- OCR Gate decision recorded: **NO-GO — deferred**. All five real invoices are
  text-based, pdfplumber is proven sufficient, Tesseract is not installed.
  No OCR code added; the extractor remains pluggable.
- Error-path audit: every known failure input responds with handled statuses
  and user-facing messaging — no 500s; invoice-isolation tests added.
- Duplicate banner no longer lists the same record twice.
- Tests: 5 new cases (TC-S5-*) — suite 169/169; manual acceptance pass over
  all five real invoices recorded in docs/04.


## 0.5.0 — Sprint 4: History, Search, Details & Delete (2026-10-06)

- Invoice history page (`/invoices`): saved invoices only, newest first
  (invoice date desc, id tiebreak), summary columns, minimal pagination
  (50/page, Older/Newer links), distinct empty states.
- Search: single box across invoice number and vendor — case-insensitive,
  fragment-based, `%`/`_` treated as literal characters (escaped parameterized
  LIKE), SQL-injection-safe.
- Detail page (`/invoices/<id>`): complete saved header, all line items,
  "View original" link serving the stored PDF (contained within `uploads/`).
- Delete: POST-only with a required confirmation step; saved-only guard;
  line items cascade (zero-orphan verified); stored file removed with
  missing-file tolerance; success/error messages throughout.
- Header navigation (Upload / History); home page links saved rows to their
  detail page.
- Edit-after-save remains deferred to a later sprint (see docs/09 §8).
- Tests: 36 new cases (TC-S4-*) — suite 164/164; five real invoices
  re-verified (65/65 fields, 23/23 line items).


## 0.4.0 — Sprint 3: Review, Edit & Atomic Save (2026-10-06)

- Review page (`/invoices/<id>/review`): every extracted field pre-filled and
  editable, with ambiguity/missing flags from the extraction draft; usable
  without JavaScript (remove checkboxes + always-present blank rows for
  adding line items).
- Server-side validation: required fields (number, date, subtotal, total),
  decimal quantization to 2 dp, strict YYYY-MM-DD dates, quantity > 0,
  unit price ≥ 0, 3-letter currency; consistency and plausibility problems
  (due < invoice date, line amount ≠ qty × unit, subtotal−discount+tax ≠
  total) produce visible warnings without blocking (E-16).
- Atomic save: header + full line set in one SQLite transaction
  (`extracted → saved`), rollback verified by an injected mid-transaction
  failure test; `extraction_json` preserved untouched as the pre-review
  audit record.
- Duplicate confirmation at save time: matching saved records by
  vendor + invoice number (case-insensitive) or file hash require an explicit
  checkbox before a second record is created.
- Security: Origin/Host check rejects cross-site POSTs with 403 (T-G).
- Upload success now redirects into review; home page offers Review links for
  extracted records.
- Tests: 40 new cases (TC-S3-*) — suite 128/128; five real invoices
  re-verified (65/65 fields, 23/23 line items).


## 0.3.0 — Sprint 2: Invoice Extraction & Parser (2026-10-06)

- Real-invoice exploration before implementation (docs/07): five sample PDFs
  profiled field-by-field; findings drove the design (currency glyph
  corruption, DD-Mon-YYYY dates, absent due dates, discount/GSTIN/bill-to
  fields, totals-inside-table structure).
- Pure parser package: whitespace/date/amount/currency/number normalization
  (Decimal at boundaries, M-3), label dictionaries with preference orders and
  word-boundary matching, geometric fallback, per-field status model
  (found/ambiguous/missing + evidence), per-strategy error containment.
- Line-item extraction from tables with item/summary separation; malformed
  rows dropped, never guessed.
- Extraction service: pdfplumber two-view → parser → atomic persist of header
  columns, line items, and resumable `extraction_json` draft; failures become
  `failed` records with readable reasons.
- Schema migration: `discount`, `vendor_tax_id`, `bill_to` columns added
  idempotently on boot.
- Upload flow now runs extraction synchronously and flashes the outcome.
- Tests: 58 new cases (unit parser + robustness + integration incl. the five
  real invoices with exact expected values) — suite 88/88; field-level
  accuracy 65/65 header fields and 23/23 line items on real samples.


## 0.2.0 — Sprint 1: Upload & Secure File Storage (2026-10-06)

- Upload page with drag-free file picker, flash feedback, and a recent-uploads
  panel (status badges per record).
- Gate sequence: presence → `.pdf` extension → 10 MB size (in-service check +
  Flask 413 backstop) → `%PDF-` magic bytes → pdfplumber openability /
  password-protection detection → 50-page cap.
- Secure storage: server-generated UUID filenames in `uploads/` only; client
  filename kept as metadata, never used for paths; single-pass SHA-256 hashing.
- Non-blocking duplicate warning on identical file content (hash match).
- Rejected uploads store nothing — no file, no database row.
- SQLite repository layer (all SQL parameterized, centralized).
- Tests: 27 new cases (16 unit, 11 integration incl. boundary) — suite 30/30;
  manual HTTP verification recorded in docs/04.


## 0.1.0 — Sprint 0: Foundation (2026-10-06)

- Archived the 2026-10-05 prototype to `../invoice-extractor-archive-2026-10-05/`
  (move, nothing deleted; git history preserved) before initializing this repo.
- Project scaffold per approved plan: Flask app factory, config (localhost-only,
  10 MB / 50-page limits), SQLite schema (`invoices`, `invoice_lines`) applied
  idempotently on boot, boot-time creation of `data/`, `uploads/`.
- Dependencies pinned: Flask 3.1.3, pdfplumber 0.11.10, pytest 9.1.1
  (Python 3.14.7 verified).
- Smoke tests (boot, home page, schema) passing; SDLC docs 01–06 in place.
