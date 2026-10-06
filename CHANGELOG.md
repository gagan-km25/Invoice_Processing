# Changelog

All notable changes to the Invoice Extractor are documented here.
The project follows the sprint plan in [docs/03-plan.md](docs/03-plan.md).

## 0.1.0 — Sprint 0: Foundation (2026-10-06)

- Archived the 2026-10-05 prototype to `../invoice-extractor-archive-2026-10-05/`
  (move, nothing deleted; git history preserved) before initializing this repo.
- Project scaffold per approved plan: Flask app factory, config (localhost-only,
  10 MB / 50-page limits), SQLite schema (`invoices`, `invoice_lines`) applied
  idempotently on boot, boot-time creation of `data/`, `uploads/`.
- Dependencies pinned: Flask 3.1.3, pdfplumber 0.11.10, pytest 9.1.1
  (Python 3.14.7 verified).
- Smoke tests (boot, home page, schema) passing; SDLC docs 01–06 in place.
