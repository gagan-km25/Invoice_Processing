# 05 — Prompt Log

Purpose: record the prompts used to drive this project, demonstrating the
"proper prompting" goal from the project charter. One entry per meaningful
prompt: phase, intent summary, artifacts produced, course-corrections caused.

---

## P-01 — Requirements phase · 2026-10-06
- **Prompt intent:** Build a local Invoice Extractor web app following a proper
  SDLC process. For now, do **only** the requirement analysis covering 12 named
  areas (objective, users/use cases, functional & non-functional requirements,
  user stories + acceptance criteria, features, edge cases, risks, security &
  privacy, assumptions, open decisions). No code, no implementation files; stop
  for approval after.
- **Artifacts:** [01-requirements-analysis.md](01-requirements-analysis.md)
- **Course-corrections:** Assistant discovered a previous (2026-10-05) partial
  project nested in the workspace; user chose **"start completely fresh"** —
  old folder untouched, all prior decisions reopened.

## P-02 — Exploration phase · 2026-10-06
- **Prompt intent:** Move to exploration; no implementation. Answer 15 technical
  questions (formats, PDF text extraction, OCR, fields, field
  identification/validation, storage, backend, frontend, component
  communication, dependencies, upload security, pre-processing validation,
  failure handling, edge cases, testing); compare approaches; recommend one
  practical approach for a same-day build; end with stack/architecture/
  components/dependencies/risks/decisions; stop for approval.
- **Artifacts:** [02-exploration.md](02-exploration.md); environment verified
  (Python 3.14.7, Tesseract absent, git 2.55).
- **Outcome:** User approved all ten decisions T-A…T-J verbatim.

## P-03 — Planning phase · 2026-10-06
- **Prompt intent:** Move to planning; no implementation. Produce a detailed
  plan covering 15 areas (directory structure, architecture responsibilities,
  schema, data flow, story mapping, sprint plan for today, task breakdown,
  dependencies, testing strategy, test categories, documentation, prompt-log
  requirements, git checkpoints, per-phase DoD, final DoD). Do not delete or
  overwrite anything; identify manual user decisions; end with a concise
  execution order; stop for approval.
- **Artifacts:** [03-plan.md](03-plan.md); seeded [05-prompt-log.md](05-prompt-log.md)
  and [06-development-log.md](06-development-log.md).
- **Pending:** Manual items M-1 (archive old folder), M-2 (real sample
  invoices), M-3 (money storage) — listed for user decision.

## P-04 — Sprint 0 kickoff · 2026-10-06
- **Prompt intent:** Plan and all three manual items approved (M-1 archive as a
  move, never delete; M-2 real invoices to arrive, never committed; M-3 REAL
  columns + Decimal boundaries). Start Sprint 0 with an explicit checklist:
  archive old project, create structure, init git, venv, dependencies, Flask
  foundation, SQLite schema, localhost-only config, test setup, README,
  .gitignore, smoke test, boot verification. Update prompt/dev logs **before**
  any change; no later-sprint features; verify everything; report before Sprint 1.
- **Artifacts:** project scaffold, venv + pinned deps, README, CHANGELOG,
  [04-test-results.md](04-test-results.md) initialized, first git commit;
  old project archived intact.
- **Notes:** First prompt executed strictly under the approved plan — the
  checkpoint discipline (logs → build → verify → report) is itself part of the
  demonstrated process.

## P-05 — Sprint 1 kickoff · 2026-10-06
- **Prompt intent:** Sprint 0 verified; proceed to Sprint 1 (Upload & Secure
  File Storage). Update logs first; no Sprint 2 extraction/parser work; keep to
  Sprint 1 scope. Specific goals: PDF-only v1, five validation gates (presence,
  extension, content, 10 MB, 50 pages), safe server-side identifiers, uploads
  only in `uploads/`, no path traversal or filesystem exposure, duplicates per
  approved requirements, clear user-facing messages, upload handling separate
  from extraction services, unit + integration tests for 12 named scenarios
  with per-case IDs/expected/actual/verdict. After: full suite run, counts,
  manual upload verification, safe-storage verification, rejection
  verification, git status, changed-file review, one Sprint 1 commit; report
  files changed, features, tests, results, verification, commit hash, issues,
  and confirmation Sprint 2 not started.
- **Artifacts:** services/uploading.py, db/repository.py, routes/uploads.py,
  upload UI, test suite (unit + integration), docs/04 results, dev log.

## P-06 — Sprint 2 kickoff · 2026-10-06
- **Prompt intent:** Proceed to Sprint 2 (Invoice Extraction & Parser) with a
  mandated phase order. **Before implementation:** update logs; review docs
  01–04; inspect all five sample PDFs with pdfplumber; never modify/rename/
  delete/commit the samples. **Phase A — real invoice exploration:** document
  per invoice: page count, plain text, ordering, tables, invoice number, date,
  vendor, vendor address, GST/tax id, bill-to, line items (description/qty/
  unit price/amount), subtotal, discount, tax rate/amount, grand total,
  currency, missing/ambiguous fields; plus extraction characteristics (text
  cleanliness, table reliability, coordinate usefulness, values split across
  lines, layout-specific strategies). Write an exploration report; do not
  assume a field exists. **Phase B — parser design before code:** normalized
  data model, per-field strategies, normalization rules (dates, currency,
  decimals, whitespace, invoice numbers), line-item strategy, missing/ambiguous
  handling, validation, confidence/status, layout discrimination, error
  reporting without crashes. **Phase C — short implementation plan, then code.**
  **Phase D — tests:** per-layout + per-field categories with IDs and real
  expected values asserted exactly (not merely non-empty). **Phase E —
  verification:** full suite, parser run on all five invoices, per-invoice
  extracted results, field-level accuracy, fixes + rerun, docs 04/06 +
  CHANGELOG updates, changed-file review, git-ignore check for samples, one
  Sprint 2 commit. **Scope control:** no review/edit UI, no save workflow, no
  management features (Sprint 3); no OCR unless exploration proves necessity
  (Tesseract unavailable — do not add silently).
- **Artifacts:** docs/07-invoice-exploration.md (findings + design + plan),
  app/services/parser/* , services/extraction.py, upload→extract wiring,
  test suite growth, docs/04 sprint 2 results, CHANGELOG.
