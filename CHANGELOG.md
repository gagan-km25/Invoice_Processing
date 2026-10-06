# Changelog

All notable changes to the Invoice Extractor are documented here.
The project follows the sprint plan in [docs/03-plan.md](docs/03-plan.md).

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
