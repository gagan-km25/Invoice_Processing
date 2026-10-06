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

## P-07 — Sprint 3 kickoff (planning phase) · 2026-10-06
- **Prompt intent:** Start Sprint 3 (review/edit → validate → save → SQLite)
  following the SDLC process — no immediate implementation code. Phase 1:
  review docs 01–07 and git history; add this prompt + sprint start to logs.
  Phase 2: define the seven given user stories (review, edit fields, edit/add/
  remove line items, validation messages, atomic save, duplicate confirmation,
  success message) without inventing major features. Phase 3: measurable
  acceptance criteria covering required fields, decimal/date/quantity/line-
  amount validation, consistency, duplicate handling, transaction rollback,
  persistence, user-visible errors, save confirmation. Phase 4: explore the
  existing schema/extraction flow (reusable columns, needed changes,
  invoice_lines sufficiency, extraction_json handling, status transitions,
  duplicate detection, review-route placement, layering) — no code changes.
  Phase 5: concise design (route flow, review page, form, server-side
  validation, line handling, duplicate confirmation, transaction boundaries,
  repository methods, success/error handling, security, test strategy) plus
  exact files to create/modify. Phase 6: scope control — no history/search,
  detail pages, delete, dashboards, OCR, auth, deployment, UI redesign.
  Report stories/AC/findings/architecture/files/tests/risks + explicit
  no-implementation confirmation; STOP for approval before coding.
- **Artifacts:** docs/08-sprint3-design.md; log updates.
- **Note:** User also approved Sprint 2 verification and the Sprint 2 commit
  at the start of this prompt cycle (commit `0a0f5cb`, single commit, tree
  clean) after the transient mid-Sprint-2 failure state was resolved and the
  premature commit was soft-reset per instruction.

## P-08 — Sprint 3 implementation · 2026-10-06
- **Prompt intent:** Design approved — implement Sprint 3 exactly per
  [08-sprint3-design.md](08-sprint3-design.md). Process requirements: no
  architecture redesign, no Sprint 4 features, layered routes → services →
  repository, parser untouched, `extraction_json` unchanged by save,
  `extracted → saved` transition, atomic header+lines transaction with
  rollback tested via injected repository failure, save-time duplicate
  detection with explicit confirmation, Origin/Host protection on POSTs,
  server-side validation authoritative, review page usable without JS,
  Sprint 0–2 functionality preserved. Test IDs TC-S3-*; regression required;
  five real invoices not to be modified; docs 04/05/06/08 + CHANGELOG +
  README updated honestly at the end. **No commit** — stop after
  verification and wait for approval.
- **Artifacts:** routes/invoices.py, services/review.py, templates/review.html,
  repository save_invoice/find_saved_duplicates, Origin check, upload redirect
  + index Review link, review styles, unit + integration test suites, docs
  updates.

## P-09 — Sprint 4 kickoff (planning phase) · 2026-10-06
- **Prompt intent:** Planning ONLY — no application code. Sprint 4 extends the
  flow with invoice history, search, details, and delete for **saved**
  invoices. Phases: review docs 01–08 + implementation + git history (confirm
  `b44d6d4`); define the seven given user stories (history, summary columns,
  search by number/vendor, detail view, delete after confirmation, safe line
  removal, empty/success/error messages); measurable ACs covering saved-only
  filtering, ordering, case-insensitive search, 404s, POST-only deletion,
  cascade line removal, SQL-injection safety, Origin protection, regression.
  Explore: existing repository methods, needed additions, schema sufficiency,
  CASCADE reliability, saved-status filtering, search implementation,
  pagination necessity, route placement, layering. Design: history/search/
  detail/delete routes, repository methods, transaction behavior, delete
  confirmation, security, empty states, test strategy (TC-S4-*). **Scope
  exclusions include edit-after-save — report any conflict with existing
  requirements instead of silently expanding scope.** Docs: P-09, dev log,
  docs/09-sprint4-design.md. STOP for approval before implementing.
- **Artifacts:** docs/09-sprint4-design.md; log updates.

## P-10 — Sprint 4 implementation · 2026-10-06
- **Prompt intent:** Design approved (edit-after-save stays deferred).
  Implement exactly per [09-sprint4-design.md](09-sprint4-design.md): history
  (saved-only, newest-first, minimal pagination 50/page), search
  (parameterized, case-insensitive, number + vendor, `%`/`_` literal,
  injection-safe), detail view (all header fields + line items), contained
  original-file serving, POST-only delete with explicit confirmation and
  saved-only guard, cascade line removal verified orphan-free, stored-file
  removal with missing-file tolerance, empty/success/error states. Layering
  routes → services → repository; existing invoices blueprint; only the four
  approved repository methods plus `services/invoices.py`; parser and Sprint 3
  review service untouched; Sprint 3 Origin protection preserved. Tests
  TC-S4-U01…/TC-S4-I01… per docs/09 §6 plus full regression. Docs updated
  honestly at the end. **No commit** — stop after verification.
- **Artifacts:** repository list_saved/count_saved/get_lines/delete_invoice,
  services/invoices.py, history/detail/confirm_delete templates, original
  serving route, delete flow, unit + integration suites, docs 04/06/09,
  CHANGELOG, README.

## P-11 — Sprint 5 kickoff (planning phase) · 2026-10-06
- **Prompt intent:** Planning ONLY for a hardening & verification sprint — no
  application code, no parser-behavior changes, no new features, no commits.
  Inspect the complete current state (docs 01–08 + README/CHANGELOG,
  implementation, git history at `6ac1de8`, the five real invoices, error
  paths). Identify realistic edge cases and failure modes; review
  error-message quality; perform a **formal, evidence-based OCR gate
  evaluation** (text-based? pdfplumber sufficient? requirement demand?
  engine availability? complexity vs. benefit?) and decide Sprint 5's OCR
  stance. Plan hardening user stories with measurable ACs (corrupt/empty/
  malformed/password PDFs, oversize/page-count, invalid types, missing
  fields, malformed values, unusual line items, DB failure, duplicates,
  deletion/search/original regressions, user-friendly errors, isolation,
  security, real-invoice acceptance), the test strategy (TC-S5-*), risks, and
  explicit scope boundaries (OCR implementation out unless the gate proves
  necessity; no Sprint 6 work). Create docs/10-sprint5-design.md; update
  docs/05 + docs/06. STOP for approval before implementing.
- **Artifacts:** docs/10-sprint5-design.md; log updates; fresh OCR-gate
  evidence gathered from the five invoices (all text-based, zero images).

## P-12 — Sprint 5 implementation · 2026-10-06
- **Prompt intent:** Planning approved — implement Sprint 5 exactly per
  [10-sprint5-design.md](10-sprint5-design.md). Approved scope only:
  US-S5-01 no-text-layer gate (a PDF that opens but has no extractable text
  must fail with the approved "likely scanned" message, never proceed as an
  all-missing extraction); US-S5-02 error-path hardening (no raw exceptions,
  no crashes, stable messages, no partial data); US-S5-03 explicit isolation
  regression tests; US-S5-04 manual acceptance over ALL FIVE real invoices
  through the full lifecycle (upload→…→delete), results recorded per invoice
  in docs/04; US-S5-05 record the OCR Gate decision **NO-GO — defer OCR**
  (no OCR implementation); US-S5-06 full regression + security verification.
  Logs first; no unapproved features; parser untouched except the approved
  gate; no schema changes; samples must remain unchanged and git-ignored;
  verify no Sprint 6 functionality and no OCR added. **Do not commit** —
  stop after verification and wait for approval.
- **Artifacts:** extraction.py no-text gate, tests/integration/
  test_sprint5_hardening.py (TC-S5-*), docs/04 sprint 5 results + manual
  acceptance evidence + OCR decision, docs/06 completion, docs/10 amendments,
  CHANGELOG, README.
