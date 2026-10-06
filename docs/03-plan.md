# 03 — Implementation Plan

Phase: **Planning** (after approved exploration, before implementation).
Date: 2026-10-06 · Status: **DRAFT — awaiting user approval**
Approved inputs: [01-requirements-analysis.md](01-requirements-analysis.md),
[02-exploration.md](02-exploration.md) (decisions T-A…T-J approved by user).

---

## 1. Final Project Directory Structure

Repo root = the workspace root. Old `invoice-extractor/` folder is moved out
first (see §13 / Manual Action M-1).

```
Invoice-Extractor/            ← project root + git repo
├── docs/
│   ├── 01-requirements-analysis.md   (approved)
│   ├── 02-exploration.md             (approved)
│   ├── 03-plan.md                    (this file)
│   ├── 04-test-results.md            (created Sprint 0; catalogue + run logs per sprint)
│   ├── 05-prompt-log.md              (created now; seeded with phases so far)
│   └── 06-development-log.md         (created now; dated build journal)
├── run.py                     # entry point: 127.0.0.1:5000
├── requirements.txt           # pinned deps (+ commented bonus-tier block)
├── pytest.ini                 # test paths, flags
├── .gitignore                 # venv, caches, data/, uploads/, sample_invoices/
├── README.md                  # setup / run / test (Sprint 0, kept accurate)
├── CHANGELOG.md               # one entry per sprint
├── app/
│   ├── __init__.py            # app factory: config, blueprints, schema init, boot dirs
│   ├── config.py              # paths, limits, flags (values in §8)
│   ├── routes/
│   │   ├── uploads.py         # GET / (upload page + status), POST /upload
│   │   └── invoices.py        # list, detail, review, save, edit, delete, file serving
│   ├── services/
│   │   ├── uploading.py       # gate sequence → store file → DB row
│   │   ├── extraction.py      # pdfplumber two-view → parser → draft persist
│   │   ├── review.py          # form validation, corrections ↔ draft merge
│   │   └── parser/
│   │       ├── __init__.py    # public API: parse(text, words, tables) → Draft
│   │       ├── normalize.py   # text cleanup; dates; amounts; currency
│   │       ├── labels.py      # label dictionaries + preference orders
│   │       ├── fields.py      # header-field strategies (one function per field)
│   │       └── lines.py       # line-item table parsing
│   ├── db/
│   │   ├── __init__.py        # connection helper: short-lived, PRAGMA foreign_keys=ON
│   │   ├── schema.sql         # idempotent DDL (§3)
│   │   └── repository.py      # all SQL lives here; parameterized only
│   ├── templates/             # base, index, review, list, detail, edit (+ partials)
│   └── static/
│       ├── css/style.css      # one hand-written stylesheet
│       └── js/main.js         # confirm dialogs only (progressive enhancement)
├── tests/
│   ├── conftest.py            # app/client fixtures on temp DB (tmp_path)
│   ├── fixtures/              # 2–3 tiny committed PDFs + corrupt/encrypted variants + text cases
│   ├── unit/                  # parser + normalize + upload gates (no Flask, no DB)
│   ├── integration/           # route flows via test client + temp DB
│   └── test_smoke.py
├── sample_invoices/           # user's real PDFs (git-ignored; see Manual Action M-2)
├── data/                      # invoices.db — created on boot (git-ignored)
└── uploads/                   # stored originals — created on boot (git-ignored)
```

## 2. Architecture & Component Responsibilities

Dependencies point one way: `routes → services → parser / repository`. No back-imports.

| Component | Responsible for | Must never do |
|---|---|---|
| `routes/` | HTTP in/out: parse request, call services, choose template/redirect, flash messages | Business logic, SQL, file access |
| `services/uploading.py` | Gate sequence (§12 of exploration), safe storage, hashing, DB row creation | Parsing invoice content |
| `services/extraction.py` | Open PDF, produce two views (text; words+coords) + tables, call parser, persist draft | Know about HTTP or forms |
| `services/parser/*` | Pure text → `Draft` (fields + per-field status + lines). No I/O of any kind | Touch files, DB, Flask |
| `services/review.py` | Validate submitted form; merge corrections into draft; produce save-ready record | SQL, file access |
| `db/repository.py` | Every SQL statement, transactions, cascade delete + file cleanup hook | HTML, extraction |
| `db/__init__.py` | Short-lived connections, `PRAGMA foreign_keys=ON`, row_factory | Hold long-open handles |
| Templates/static | Presentation; flags for `ambiguous`/`missing`/`failed`; all autoescaped | Contain logic beyond loops/conditionals |

## 3. Database Schema & Relationships

As specified in exploration §7, finalized:

- `invoices` — `id` PK · `file_hash` (indexed, **not** unique) · `original_filename` ·
  `stored_filename` · vendor · invoice_number · invoice_date · due_date (ISO text) ·
  currency · subtotal · tax · tax_rate · total · `status CHECK IN
  ('uploaded','extracted','saved','failed')` · `extraction_json` (per-field
  status/source draft) · `error_message` · page_count · created_at · updated_at
- `invoice_lines` — `id` PK · `invoice_id` FK → invoices.**ON DELETE CASCADE** ·
  line_number · description · quantity · unit_price · amount
- Indexes: `file_hash`, `invoice_number`; DDL idempotent (`CREATE TABLE IF NOT EXISTS`),
  executed on every boot; **money stored as REAL, all parsing/validation/comparison
  through `decimal.Decimal` at application boundaries** (T-E — documented here and in
  `schema.sql` comments); timestamps ISO-8601.

## 4. Data Flow (upload → validation → extraction → review → database)

```
POST /upload
 1. size gate (MAX_CONTENT_LENGTH)          fail→ flash "too large", nothing stored
 2. presence / 0-byte check                 fail→ flash "could not be read"
 3. extension whitelist (.pdf)              fail→ flash "unsupported type"
 4. magic bytes (%PDF-)                     fail→ flash "not a valid PDF"
 5. pdfplumber opens; pages 1..50;
    not encrypted                           fail→ specific message per cause
 6. store file → uploads/<uuid>.pdf;
    compute SHA-256
 7. INSERT invoices(status='uploaded')      → id
 8. extract text + words + tables           exception→ status='failed', reason stored
 9. parser.parse() → Draft (fields,
    per-field status, lines, flags)
10. UPDATE status='extracted',
    extraction_json=draft
11. redirect → GET /invoices/<id>/review
      │  (render: values + found/ambiguous/missing flags; draft is server-side,
      │   so refresh/back-safe; user may return later without re-upload)
POST /invoices/<id>/save
12. review.validate_form()                  fail→ re-render with per-field errors
13. merge corrections over draft
14. duplicate check: file_hash OR
    (vendor + invoice_number)               match→ warning page; save only on confirm
15. BEGIN; UPDATE invoice columns
    (status='saved'); DELETE+INSERT lines; COMMIT    (atomic, NFR-5)
16. redirect → GET /invoices/<id>  (detail)
```

Edit-after-save (`POST /invoices/<id>/edit`) reuses step 12's validator against
columns; delete = confirmation page → `DELETE` (lines cascade) + unlink stored
file (D-F). Origin/Host check wraps every POST (T-G).

## 5. User Story → Feature Mapping

| Story | Tier | Delivered by | Sprint |
|---|---|---|---|
| US-1 upload | Must | uploading gates 1–7 + index page | 1 |
| US-2 extract | Must | extraction + parser + status model | 2 |
| US-3 review/correct | Must | review page + review.py | 3 |
| US-4 save (+dup warning) | Must | review.py + repository transaction | 3 |
| US-5 list | Must | invoices.py `/invoices` + list.html | 4 |
| US-6 detail + original | Must | detail route + file serving | 4 |
| US-7 clear failures | Must | gate messages + failed status + taxonomy | 1–3 (tested 5) |
| US-8 edit | Should | edit route reusing review form | 4 |
| US-9 delete | Should | delete route + cascade + file unlink | 4 |
| US-10 search/filter/sort | Should | list query params (SQL LIKE / ORDER BY) | 4 |
| US-11 OCR | Could | gated spike (T-I) | only if gate passes |
| US-12 CSV export | Could | `/invoices/export.csv` | only if time remains |

## 6. Sprint / Phase Plan (today)

| Sprint | Goal | Exit checkpoint | Time box |
|---|---|---|---|
| 0 | Foundation: archive old folder (M-1), structure, venv+deps, factory+config+schema, boots, smoke test, git init + commit | app serves 200; `pytest` green; commit | ~40 min |
| 1 | Upload & store: full gate sequence, safe storage, hashing, `uploaded` rows, upload page + error flashes, gate unit tests | happy path + all reject paths tested; commit | ~45 min |
| 2 | Extraction engine: two-view pdfplumber, normalize module, 8 header-field strategies, per-field status, draft persistence; parser unit tests | parser suite green on text fixtures; real-PDF spike check; commit | ~90 min |
| 3 | Review & save: read-only results become editable form, validation, corrections merge, duplicate warning, atomic save; integration tests | US-2/3/4 ACs pass; commit | ~60 min |
| 4 | Manage: list (+search/filter/sort), detail + view original, edit, delete; integration tests | US-5/6/8/9/10 ACs pass; commit | ~60 min |
| 5 | Hardening: edge-case pass (E-1…E-25 vs implementation), failure taxonomy polish, full manual acceptance on real invoices (M-2), results logged | US-7 verified; manual pass recorded; commit | ~45 min |
| 6 | Final: full suite + results doc, README/CHANGELOG accuracy (fresh-setup check), docs complete, final review vs DoD | all Must ACs checked; docs complete; final commit + tag | ~40 min |
| X | OCR spike (T-I gate): **only if** Sprint 4 exit passed **and ≥2 h remain** — else explicitly skipped with reason logged | — | gated |

Checkpoint rule: if a sprint's time box overruns by >50%, stop, record status in
the development log, and decide with the user what to drop (Should-tier first).

## 7. Task Breakdown

**Sprint 0 — Foundation**
- S0-T1 Move `invoice-extractor/` out to `../invoice-extractor-archive-2026-10-05/` (M-1, after approval)
- S0-T2 Create structure per §1; `.gitignore`; empty `data/`, `uploads/`, `sample_invoices/`
- S0-T3 `venv` + `pip install` Flask pdfplumber pytest; pin in `requirements.txt` (bonus block commented)
- S0-T4 `config.py` (paths; `MAX_CONTENT_LENGTH` 10 MB; `PAGE_LIMIT` 50; `DEBUG=True`, `use_reloader=False`, host `127.0.0.1`)
- S0-T5 app factory; `db/__init__.py` + `schema.sql`; boot creates dirs + schema
- S0-T6 `run.py`; `pytest.ini`; `tests/test_smoke.py` (factory boots, `/` 200, schema exists)
- S0-T7 README + CHANGELOG skeletons; docs 04/05/06 initialized
- S0-T8 `git init`, first commit

**Sprint 1 — Upload & store**
- S1-T1 `uploading.py`: gates in order (size→presence→extension→magic→open/pages/encrypted)
- S1-T2 UUID storage + original-name metadata + SHA-256
- S1-T3 `repository.py`: insert row, fetch by id, update status/error
- S1-T4 `uploads.py`: `GET /` (page + recent-status panel), `POST /upload`
- S1-T5 `index.html` + `base.html` + `style.css` (upload form, flash area)
- S1-T6 Unit tests: each gate × (pass + fail); fake files for magic-byte cases
- S1-T7 Integration: upload happy path stores file+row; every reject stores nothing

**Sprint 2 — Extraction engine**
- S2-T1 `extraction.py`: pdfplumber open, page loop (≤ limit), text + `extract_words` + `extract_table` per page
- S2-T2 `normalize.py`: whitespace/ligature cleanup; date formats (US, ISO, "Mar 4, 2025", "4 Mar 2025") with ambiguity flagging; amount formats (`1,234.56`, `1.234,56`, `$`, `(x)`); currency symbol/code mapping
- S2-T3 `labels.py`: dictionaries + preference orders (total: Due/Amount Due/Balance > Grand Total > Total)
- S2-T4 `fields.py`: 8 strategies (label→same-line→geometric→pattern), per-field status `found/ambiguous/missing` + source
- S2-T5 `lines.py`: table header-keyword detection, row validation, drop-with-flag
- S2-T6 `parser/__init__.py`: Draft dataclass + consistency checks (subtotal+tax≈total; due ≥ invoice date)
- S2-T7 Draft persisted to `extraction_json`; failures → `failed` + reason
- S2-T8 Unit tests (bulk of suite): ~45–60 cases across normalize/fields/lines incl. multi-candidate totals, ambiguous dates, European amounts
- S2-T9 Committed PDF fixtures (2–3 small synthetic invoices) + smoke extraction test

**Sprint 3 — Review & save**
- S3-T1 `review.html`: all fields editable, flags rendered (ambiguous/missing/failed styling), line items editable rows
- S3-T2 `review.py`: server-side validation (dates, Decimal amounts, required: invoice_number + total), corrections-merge
- S3-T3 Duplicate warning: hash OR vendor+number → confirm page (T-E/T-D: indexed lookups)
- S3-T4 Atomic save transaction; status → `saved`; success flash → detail redirect
- S3-T5 Origin/Host check decorator on all POSTs (T-G)
- S3-T6 Integration tests: review renders draft; correction stored (AC-3.2); invalid blocked (AC-3.3); duplicate warning (AC-4.2); atomicity rollback test

**Sprint 4 — Manage invoices**
- S4-T1 List page: newest first, status column, empty state (AC-5.x)
- S4-T2 Search `q` (vendor/number LIKE), date-range filter, sort (date/total) (AC-10.x)
- S4-T3 Detail page: header + lines + "view original" via contained file serving (AC-6.x)
- S4-T4 Edit: reuse review form against saved columns (AC-8.x)
- S4-T5 Delete: confirmation → DB delete (cascade) + file unlink (AC-9.x, D-F)
- S4-T6 Integration tests for all of the above incl. delete-cascades-and-unlinks

**Sprint 5 — Hardening & manual acceptance**
- S5-T1 Walk E-1…E-25 against implementation; fix gaps; add missing tests (corrupt/encrypted fixtures, no-text-layer path, Unicode vendor, long values)
- S5-T2 Failure-message polish pass (US-7: problem + next step, every mode)
- S5-T3 **Manual acceptance pass on real invoices** (M-2) — scripted checklist = Must ACs; results logged in docs/04
- S5-T4 OCR gate decision recorded (go/no-go per T-I)

**Sprint 6 — Final tests, docs, review**
- S6-T1 Full suite run; results recorded; flaky/failing = fix before proceeding
- S6-T2 README verified against a clean-venv setup; CHANGELOG finalized
- S6-T3 Docs complete: 04 results, 05 prompts, 06 dev log; requirement-traceability glance (US ↔ tests)
- S6-T4 Final review vs §15 DoD; retrospective summary for the user; final commit + `v1.0.0` tag

**Sprint X (gated) — OCR**: pypdfium2 raster → pytesseract → same parser; `source=ocr` flags; "not installed" message path. Only after S4 exit with ≥2 h remaining (T-I).

## 8. Dependencies to Install

```
# requirements.txt (Must tier)
Flask==3.1.*        # web framework            (pin exact at install)
pdfplumber==0.11.*  # PDF text/words/tables    (pin exact at install)
pytest==8.*         # dev/test
# Bonus tier (Sprint X only, uncommented then):
# pypdfium2         # rasterize pages for OCR
# pytesseract       # Tesseract wrapper (+ system Tesseract install)
```

Config values locked: `MAX_CONTENT_LENGTH = 10 MB`, `PAGE_LIMIT = 50`,
`HOST = 127.0.0.1`, `DEBUG = True`, `use_reloader = False` (T-H / exploration).

## 9. Testing Strategy

Per exploration §15, executed as: parser = pure text fixtures (bulk of cases,
fast); gates = crafted fake files; integration = Flask test client + **temporary
SQLite in `tmp_path`** (real `data/invoices.db` never touched by tests); smoke on
every change; manual acceptance scripted from Must ACs. Commit only on green.

## 10. Test Case Categories (catalogue grows in docs/04)

| Category | ~Cases | Covers |
|---|---|---|
| Normalization: dates | 8 | US/ISO/textual, ambiguous flag, invalid |
| Normalization: amounts | 8 | US, European, symbol-prefixed, negatives, junk |
| Normalization: currency | 5 | codes, symbols, absent → flagged |
| Field strategies (×8 fields) | 40 | found / missing / ambiguous / multi-candidate / geometric-only |
| Line items | 6 | table found, header variants, bad rows dropped+flagged, no table |
| Consistency checks | 4 | sum mismatch, due < invoice, negative total |
| Upload gates | 9 | each gate pass+fail, magic-byte fakes |
| Integration flows | 14 | upload→save happy; each reject; duplicate; atomic rollback; edit; delete-cascade; search/sort |
| Failure modes | 8 | corrupt, encrypted, no-text-layer, parser exception, oversized, missing dirs |
| Smoke | 3 | boot, schema, routes |
| Manual acceptance | Must-AC checklist | real invoices, end of Sprint 5 |

## 11. Documentation Maintained

| Doc | Created | Kept current |
|---|---|---|
| 01-requirements / 02-exploration / 03-plan | approved already | frozen (amend only by user-approved change) |
| 04-test-results.md | Sprint 0 | every sprint: catalogue + run log + output summary |
| 05-prompt-log.md | now | every meaningful prompt, per phase |
| 06-development-log.md | now | dated entries per sprint with decisions/deviations |
| README.md / CHANGELOG.md | Sprint 0 | every sprint; README re-verified at S6 |
| Decision record | — | T-A…T-J live in 02-exploration §20 (single source; no separate log to duplicate) |

## 12. Prompt-Log Requirements

Every meaningful user prompt gets an entry: date · phase · one-paragraph summary
of the prompt's intent (not verbatim unless short) · artifacts produced · any
course-correction it caused. Seeded today with the requirements, exploration, and
planning prompts. Purpose per user's stated goal: demonstrate proper prompting as
part of the SDLC record.

## 13. Git / Version-Control Checkpoints

- **Pre-condition (M-1):** old folder moved out **before** `git init` — no nested repo.
- Commits: one per sprint exit, message `Sprint N: <goal>`; tests green before every commit; never commit on red.
- `.gitignore` from S0-T2 covers: `venv/`, `__pycache__/`, `.pytest_cache/`, `data/`, `uploads/`, `sample_invoices/` (real invoices never committed — privacy, requirements §10.10).
- No remote (local only). Final: `v1.0.0` tag at project DoD.
- Old folder's own history is preserved untouched inside the archive location.

## 14. Definition of Done — per Sprint

Common to all: sprint tasks complete · its stories' ACs pass · new tests green, full suite green · docs/04 run logged · dev log + prompt log updated · committed.
Per-sprint additions: **S0** fresh boot works; **S1** nothing stored on any reject path; **S2** parser green on all text fixtures + real-PDF spike sane; **S3** corrections—not raw extractions—are what persist (AC-3.2); **S4** delete removes row *and* file; **S5** manual acceptance on real invoices recorded; **S6** final DoD below.

## 15. Final Definition of Done — Complete Project

1. All **Must** ACs (US-1…US-7) pass: automated where possible + recorded manual pass on real invoices
2. All **Should** ACs (US-8…US-10) pass
3. **Could** tier explicitly done or skipped **with reason logged** (T-I gate record)
4. Full test suite green; results catalogue complete in docs/04; no skipped/xfixed tests without logged reason
5. Fresh-machine setup reproducible: clean venv → `pip install -r requirements.txt` → `python run.py` works (verified in S6)
6. Privacy posture intact: localhost-only binding, nothing external, no real invoice data in git
7. Docs complete and truthful: 01–06 + README + CHANGELOG; prompt log shows the full SDLC trail
8. Final review delivered: what was built, test evidence, known limitations (e.g., vendor accuracy, OCR skipped), and retrospective vs. the user's stated improvement goals

---

## Manual Decisions / Actions Required from User

| # | Item | When | Options |
|---|---|---|---|
| **M-1** | Approve moving old `invoice-extractor/` → `../invoice-extractor-archive-2026-10-05/` (move, **not delete**; git history preserved; verified empty of data) | Sprint 0 start | Approve move · move it yourself · leave in place (then repo root must become a new subfolder — tell me which) |
| **M-2** | Provide 3–5 real invoice PDFs into `sample_invoices/` for parser tuning + the Sprint-5 manual pass | by Sprint 2 | Provide real ones · proceed with synthetic fixtures only (less realistic tuning) |
| **M-3** | Confirm money storage choice now that T-E wording allows either: **REAL columns + Decimal boundaries** (recommended) or INTEGER cents | now | REAL (rec) · cents |

## Execution Order (approved plan → implementation sequence)

**S0 foundation → S1 upload/store → S2 extraction/parser → S3 review/save → S4 manage → S5 hardening + manual acceptance → S6 final tests/docs/review → (X: OCR only if gated in).**
