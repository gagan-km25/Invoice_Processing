# Invoice Processing 

A **local-only** invoice-processing web application: upload invoices (PDF,
JPG, JPEG, PNG), have their details extracted (configured AI extraction for
scans/images and text PDFs; a local rules parser as offline fallback for
text PDFs), validate them automatically, detect duplicates, review and
correct the results, submit them for approval, and approve or reject them —
with a full audit history. Built as a complete, documented SDLC exercise.

- Runs at `http://127.0.0.1:5000` — localhost only, single user, no
  deployment.
- Storage: SQLite (`data/invoices.db`, **schema v3**) + original files kept
  in `uploads/` (git-ignored).
- Status: **enhancement sprints E0–E5 implemented and accepted; E6
  documentation/verification work committed** (offline-tested — live API
  smoke, browser walkthrough and §23 demonstration still pending). **Live verification still pending:** the real
  GLM API smoke test and browser-level UI walkthrough (see
  [docs/16-e6-demo-script.md](docs/16-e6-demo-script.md) and
  [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md)).

## Features

- **Upload (PDF, JPG, JPEG, PNG).** Type/size/empty-file gates with content
  signatures; 10 MB limit; upload returns immediately — processing runs in
  a background worker.
- **Extraction.** Text-layer PDFs are processed by the configured GLM model
  (strict JSON response validation, one re-ask on malformed output,
  size-capped raw response retained locally); without a configured key, a
  local rules parser handles text PDFs. Scanned PDFs and images go through
  GLM vision on rasterised pages (≤ 3 pages). Malformed AI responses never
  crash the app — they fail safely with a recorded, user-safe reason.
- **Business validation.** Currency extraction supports explicit labels
  (`Currency: INR`) and amount tokens (`₹`, `Rs.`, `Rs`, `INR`, `$`, `€`,
  `£`, `¥`) with Indian digit grouping (`1,25,000.00`), validated against
  an offline ISO 4217 dataset (minor-unit aware: zero-decimal currencies
  such as JPY keep their precision); ambiguous symbols (¥ = JPY or CNY)
  are flagged, never guessed. Mandatory fields (number, date, vendor,
  currency, total); amount equations (`subtotal + tax = total`, or
  `subtotal − discount + tax = total` when a discount applies) with a
  configurable tolerance (default ₹0.01); date rules; GSTIN format check
  when present. Verdicts: Passed / Warning / Failed, each finding shown on
  the detail page.
- **Duplicate detection.** Classifies invoices as Exact (same vendor +
  invoice number) or Possible (same vendor + total + date) against stored
  records, with the matched records named. Informational only — it never
  blocks processing. The save flow separately asks for confirmation when
  another record shares the vendor + invoice number or the same file
  content.
- **Review & correction.** The review page pre-fills every extracted field
  (ambiguous/missing flagged), including per-line tax; corrections are
  validated and saved atomically.
- **Approval workflow.** Submit a completed or validation-failed invoice
  for approval: totals below ₹1,00,000 are routed to the **manager**
  approver, ₹1,00,000 or above to **finance**. The routed approver approves
  or rejects it from a role-filtered queue; rejection requires a reason,
  which is stored and displayed. Invalid transitions (e.g. approving an
  already-approved invoice) are refused with no changes.
- **Roles.** Session role labels — `vendor` (default), `approver:manager`,
  `approver:finance` — switchable in the header. A workflow mechanism, not
  authentication: wrong-role actions are refused (403) with no changes.
- **History & detail.** All-status invoice list with exact-status filter,
  search, ID and created-date columns; a detail page with the extracted
  fields, validation findings, duplicate explanation, approval state,
  rejection reason, audit timeline, and (when retained) the raw AI
  response — collapsed and escaped.
- **Deletion.** Records can be deleted (with confirmation) from any status
  except `uploaded`/`processing`; deletion removes the record, its line
  items, audit entries, and the stored file (file removal is best-effort).

## Invoice lifecycle

```
uploaded → processing → completed ─┬─→ (review & save keeps it completed)
                                   └─→ pending_approval ─→ approved
                                ┌─→ validation_failed ─┘        ↘ rejected
processing → failed (reprocessable)
```

Transitions are controlled by a single state machine (`app/services/
workflow.py`); invalid transitions are impossible. Every lifecycle change
writes an audit entry in the same transaction.

## Configuration

All configuration lives in `app/config.py`; the AI-related values are
environment-overridable (see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `ZAI_API_KEY` | *(empty)* | GLM (Z.ai) API key. Empty → text PDFs use the local rules parser; scans/images fail with a clear "not configured" message |
| `ZAI_BASE_URL` | `https://api.z.ai/api/paas/v4/` | GLM API endpoint |
| `ZAI_TEXT_MODEL` / `ZAI_VISION_MODEL` | `glm-4.6` / `glm-4.5v` | Models to confirm against the real account |
| `ZAI_TIMEOUT_SECONDS` / `ZAI_MAX_TOKENS` | 60 / 4000 | GLM call limits |
| `VISION_MAX_PAGES` | 3 | Rasterised pages per scanned PDF |
| `RAW_RESPONSE_MAX_BYTES` | 65536 | Retained raw-response cap |
| `APPROVAL_THRESHOLD` | `100000.00` | Manager/finance routing boundary (₹) |
| `WORKER_*` | autostart on / 3 attempts / 1 s backoff | Background-worker behaviour |
| `MAX_CONTENT_LENGTH` | 10 MB | Upload size limit |

Invoice content leaves the machine **only** during GLM extraction; nothing
is stored or logged externally (see KNOWN_ISSUES K-3/K-4).

## Setup & Run

```bash
# 1. Create the virtual environment (first time only)
python -m venv venv

# 2. Install dependencies (Flask, pdfplumber, pytest, requests — pinned)
venv\Scripts\python -m pip install -r requirements.txt

# 3. Optional: configure GLM extraction
copy .env.example .env    # then set ZAI_API_KEY (and model names if needed)

# 4. Start the app
venv\Scripts\python run.py
```

Open **http://127.0.0.1:5000**. On first boot the app creates
`data/invoices.db` (schema applied/migrated idempotently) and `uploads/`.

> **Database notice:** this repository's live database is currently at
> schema v2 by recorded decision. The next application start upgrades it
> to schema v3 automatically; per project policy this requires explicit
> authorisation and a fresh timestamped backup first (see
> docs/KNOWN_ISSUES.md K-9/NFR-E7). Tests always use temporary databases.

## Run Tests

```bash
venv\Scripts\python -m pytest -q
```

The suite (478 tests, all passing) always runs against
a **temporary** database and temp folders — real data is never touched.
These are offline tests: they mock the GLM HTTP calls. The **live API smoke
test and a browser-level walkthrough are still pending** (tracked in
docs/TEST_PLAN.md).

## Project Layout

```
Invoice-Extractor/
├── run.py                  # entry point → http://127.0.0.1:5000
├── requirements.txt        # pinned dependencies
├── .env.example            # GLM configuration template
├── pytest.ini
├── docs/                   # SDLC documentation (see below)
├── app/
│   ├── __init__.py         # app factory, error handlers, role context
│   ├── config.py           # localhost binding, limits, GLM settings
│   ├── routes/             # uploads, invoices, approvals, session
│   ├── services/           # uploading, extraction, review, validation,
│   │                       # duplicates, approvals, roles, pipeline,
│   │                       # workflow, audit, applog, parser/
│   ├── db/                 # schema.sql, migrations (v1→v2→v3), repository
│   ├── templates/          # Jinja pages
│   └── static/             # local CSS/JS only — works offline
├── tests/                  # pytest suite (temp DB) + fixtures
├── sample_invoices/        # real invoice samples — git-ignored, stay local
├── data/                   # invoices.db — created at boot, git-ignored
└── uploads/                # stored original files — created at boot, git-ignored
```

## Documentation (SDLC)

Enhancement documents (current):

| Doc | Contents |
|---|---|
| [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) | Requirement inventory (R-001…R-074) with traceability + statuses |
| [docs/USER_STORIES.md](docs/USER_STORIES.md) | User stories, acceptance criteria, §24 acceptance matrix |
| [docs/SPRINT_PLAN.md](docs/SPRINT_PLAN.md) | Approved sprint plan + per-sprint outcomes and task records |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Architecture, state model, migrations, roles, AI integration |
| [docs/TEST_PLAN.md](docs/TEST_PLAN.md) | Test strategy, recorded runs, §16 coverage map, accuracy checklist |
| [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md) | Open/closed issues with mitigations (incl. migration incident K-9) |
| [docs/15-e3-amount-validation-decision.md](docs/15-e3-amount-validation-decision.md) | Decision record: discount-aware amount validation |
| [docs/16-e6-demo-script.md](docs/16-e6-demo-script.md) | §23 demonstration script (draft; run pending) |
| [CLAUDE_USAGE.md](CLAUDE_USAGE.md) | Claude Code usage record (exploration → review) |

Original v1 documents (preserved unmodified): `docs/01-requirements-analysis.md`,
`docs/02-exploration.md`, `docs/03-plan.md`, `docs/04-test-results.md`,
`docs/05-prompt-log.md`, `docs/06-development-log.md`,
`docs/07-invoice-exploration.md`, `docs/08-sprint3-design.md`,
`docs/09-sprint4-design.md`, `docs/10-sprint5-design.md`,
`docs/11-final-verification-plan.md`, `docs/12-retrospective.md`,
`docs/13-evaluation-q-and-a.md`, plus `docs/14-execution-commands.md`
(execution log).

## Important Notes

- **Live verification:** the GLM integration is fully offline-tested
  (HTTP mocked) but has not yet been exercised against the real API; the UI
  has been verified at HTML/flow level, not in a browser session. Both are
  tracked for Sprint E6 (docs/TEST_PLAN.md §3).
- **Everything stays on this machine** except invoice content sent to the
  configured GLM endpoint during extraction; `data/`, `uploads/`, and
  `sample_invoices/` are git-ignored — real invoices are never committed.
- **OneDrive caution:** this folder is inside OneDrive sync. Sync locking can
  corrupt SQLite databases under heavy use. If you see DB errors, pause OneDrive
  while the app or tests run, or exclude this folder from sync.
- **Git note:** all accepted sprint work is committed on branch
  `enhancement/assignment` (E0 `daeb9c2`, E1 `b4bbee9`, E2 `c5d6bee`,
  E3–E5 `795e5bf`, E6 documentation `c197e11`, parser fix `2e9b85a`) —
  local only, no remote.
- The git repo is **local only** — there is no remote.
