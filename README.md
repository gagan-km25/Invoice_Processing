# Invoice Extractor

A **local-only** web application for uploading invoices, automatically extracting
their details, reviewing/correcting them, and storing them in a local database.
Built as a complete, documented SDLC exercise: requirements → exploration →
user stories → design → sprint planning → implementation → testing →
verification → retrospective (see Documentation below).

- Runs at `http://127.0.0.1:5000` — no cloud, no deployment, no external calls.
- Extraction: rules/regex on the PDF text layer, with word-coordinate label
  matching (two-view extraction). PDF-only for the required scope; OCR is a
  gated bonus tier.
- Storage: SQLite (`data/invoices.db`) + original files kept in `uploads/`.

## Current Status

**Sprint 0 — project scaffold (complete).** The app boots, the database schema
is in place, and smoke tests pass. Features arrive per the approved plan
([docs/03-plan.md](docs/03-plan.md)):

| Sprint | Feature | Status |
|---|---|---|
| 0 | Scaffold, DB schema, docs | ✅ Done |
| 1 | Upload & store invoices | ✅ Done |
| 2 | Automatic field extraction | ✅ Done |
| 3 | Review & save to database | ✅ Done |
| 4 | History, search, details & delete | ✅ Done |
| 5 | Hardening, edge cases & OCR gate | ✅ Done (OCR gate: NO-GO — deferred, see docs/10) |
| 6 | Final verification, docs & retrospective | ✅ Done |
| X | OCR (gated — gate result: deferred, docs/10 §5) | Deferred |

## Prerequisites

- **Python 3.14** (verified on 3.14.7, Windows 11) — check with `python --version`
- No other system dependencies. **OCR was evaluated and deferred** (Sprint 5
  OCR Gate: NO-GO — all verified invoices are text-based; see
  [docs/10-sprint5-design.md](docs/10-sprint5-design.md) §5). Scanned PDFs are
  detected and rejected with a clear "likely a scan" message.

## Setup & Run

```bash
# 1. Create the virtual environment (first time only)
python -m venv venv

# 2. Install dependencies
venv\Scripts\python -m pip install -r requirements.txt

# 3. Start the app
venv\Scripts\python run.py
```

Open **http://127.0.0.1:5000** in your browser. Stop the server with `Ctrl+C`.
On first boot the app creates `data/invoices.db` (schema applied idempotently)
and the `uploads/` folder — no manual setup steps.

**Workflow:** upload a PDF → the app extracts the fields → the **review page**
opens with everything pre-filled and flagged where the extractor was unsure →
correct anything you like → **Save invoice** stores it (header + line items in
one transaction). Use **History** to browse, search, open, or delete saved
invoices — deleting asks for confirmation and removes the record, its line
items, and the stored file.

## Run Tests

```bash
venv\Scripts\python -m pytest -v
```

Tests always run against a **temporary** database and temp folders — your real
data is never touched.

## Project Layout

```
Invoice-Extractor/
├── run.py                  # entry point → http://127.0.0.1:5000
├── requirements.txt        # pinned dependencies
├── pytest.ini
├── docs/                   # SDLC documentation (see below)
├── app/
│   ├── __init__.py         # app factory
│   ├── config.py           # localhost binding, limits, paths
│   ├── routes/             # blueprints (Sprints 1–4)
│   ├── services/           # uploading, extraction, review, parser/ (Sprints 1–3)
│   ├── db/                 # schema.sql + short-lived connection helpers
│   ├── templates/          # Jinja pages
│   └── static/             # local CSS/JS only — works offline
├── tests/                  # pytest suite (temp DB) + fixtures
├── sample_invoices/        # real invoice samples — git-ignored, stay local
├── data/                   # invoices.db — created at boot, git-ignored
└── uploads/                # stored original files — created at boot, git-ignored
```

## Documentation (SDLC)

| Doc | Contents |
|---|---|
| [docs/01-requirements-analysis.md](docs/01-requirements-analysis.md) | Approved requirements (12 areas) |
| [docs/02-exploration.md](docs/02-exploration.md) | Technical exploration, approach comparison, decisions T-A…T-J |
| [docs/03-plan.md](docs/03-plan.md) | Approved implementation plan, sprints, DoD |
| [docs/04-test-results.md](docs/04-test-results.md) | Test catalogue + recorded runs |
| [docs/05-prompt-log.md](docs/05-prompt-log.md) | Log of prompts used during development |
| [docs/06-development-log.md](docs/06-development-log.md) | Dated build journal |
| [docs/07-invoice-exploration.md](docs/07-invoice-exploration.md) | Real-invoice exploration + parser design |
| [docs/08-sprint3-design.md](docs/08-sprint3-design.md) | Sprint 3 review/save design |
| [docs/09-sprint4-design.md](docs/09-sprint4-design.md) | Sprint 4 history/search/detail/delete design |
| [docs/10-sprint5-design.md](docs/10-sprint5-design.md) | Sprint 5 hardening design + OCR gate decision |
| [docs/11-final-verification-plan.md](docs/11-final-verification-plan.md) | Final verification plan, traceability matrix, evidence |
| [docs/12-retrospective.md](docs/12-retrospective.md) | Evidence-based project retrospective |
| [docs/13-evaluation-q-and-a.md](docs/13-evaluation-q-and-a.md) | Evaluation Q&A: Claude Code usage + project deep-dive |

## Important Notes

- **Everything stays on this machine.** No data, prompts, or files leave your
  computer; `data/`, `uploads/`, and `sample_invoices/` are git-ignored — real
  invoices are never committed.
- **OneDrive caution:** this folder is inside OneDrive sync. Sync locking can
  corrupt SQLite databases under heavy use. If you see DB errors, pause OneDrive
  while the app or tests run, or exclude this folder from sync (risk T-3,
  [docs/02-exploration.md](docs/02-exploration.md) §7).
- The git repo is **local only** — there is no remote.
- A previous 2026-10-05 prototype was archived (move, nothing deleted) to
  `../invoice-extractor-archive-2026-10-05/` with its git history intact.
