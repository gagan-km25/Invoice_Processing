# CLAUDE_USAGE — Invoice Processing System Enhancement

How Claude Code was used on the enhancement assignment, with only genuine
events. This file grows sprint by sprint; sections for work that has not
happened yet say so explicitly rather than containing invented material.
The pre-enhancement build's prompt history is preserved untouched in
docs/05-prompt-log.md (see also docs/13-evaluation-q-and-a.md).

## Codebase exploration (2026-10-12)

Claude Code explored the existing repository at the assignment's start,
without modifying anything, and produced a report that established:

- The repo is the completed v1 "Invoice Extractor" (Sprints 0–6), i.e. the
  "existing basic application" the enhancement assignment starts from, and
  the assignment's own scope (async processing, validation verdicts,
  duplicate classification, approval workflow, roles, audit history) was
  absent — confirmed by reading routes/services/schema and by targeted
  searches, not assumed.
- The assignment file was located outside the repo as
  `Invoice_Processing_Enhancement_Assignment.txt` on the Desktop and read
  in full (25 headings, 21 acceptance criteria).
- The full test suite was executed (169 passed) rather than trusted from
  documentation.
- Verification of external capabilities before design: the Z.ai GLM API was
  checked against official docs (endpoint, auth, `response_format` JSON
  mode — text models only; vision models accept base64 images in
  jpg/png/jpeg), and the local venv was inspected (pypdfium2 + pillow
  present; no HTTP client), which grounded the JPG/PNG and scanned-PDF
  design without assuming model capabilities.

## Planning (2026-10-12)

Claude Code produced a full requirement→task map (25 headings), a
dependency-aware sprint plan (E0–E6), the four-dimension state model, the
database migration strategy, and a 21-row acceptance-criteria traceability
matrix. Across three review rounds the user required corrections that
Claude Code then designed: separate traceability rows per AC; recovery
redesign (worker-only transitions); recovery **job ownership** (only
recovery-designated jobs may resume stale `processing` invoices); role/access
route map with honest limits; strengthened migration tests; raw-response
privacy controls beyond HTML escaping; a structural log allowlist plus a
single traceback logger fed only sanitised exceptions. The approved plan is
docs/SPRINT_PLAN.md + docs/ARCHITECTURE.md.

## Implementation (genuine record, ongoing)

- **Sprint E0 (2026-10-12).** Claude Code implemented the versioned schema
  migration (v1→v2 table rebuild with status mapping and audit rows), the
  workflow status machine and approval-routing rule, the audit catalogue,
  environment-based AI configuration with placeholder `.env.example`, and
  51 new tests, then ran them: first run 2 failed / 49 passed — both
  failures were real defects the tests caught (missing v1 index recreation
  in the migration; an over-broad assertion) — after fixes 51/51, and the
  full suite 220 passed. Claude Code also executed the copied-database
  rehearsal against a backup copy of the real `data/invoices.db`
  (PASS; original untouched).

## Debugging (genuine cases — to be appended as they occur)

Two meaningful debugging cases are required by the assignment (§21). They
will be documented here with Problem/Investigation/Root Cause/Solution/
Testing **only as they genuinely happen**. One genuine case already
occurred during Sprint E0 and is recorded below; more will be added if and
only if they occur.

### D-1 — Migration omitted the v1 indexes (Sprint E0, 2026-10-12)

- **Problem:** `test_migrated_schema_matches_fresh_schema` (TC-MIG-09)
  failed: a migrated v1 database lacked `idx_invoices_hash` and
  `idx_invoices_number`.
- **Investigation:** Compared `sqlite_master` index sets between a fresh v2
  database and a migrated copy; the migration's index step only created the
  new v2 indexes.
- **Root cause:** The rebuild recreated the table but not the two v1
  indexes; only the schema-equivalence test compared index sets, which is
  why it alone caught the gap.
- **Solution:** `app/db/migrations.py` now recreates both v1 indexes
  alongside the v2 ones.
- **Testing:** Re-ran the new-test file (51/51) and the full suite
  (220 passed); TC-MIG-09 now guards against future drift.

## Refactoring (§21 requires at least one genuine area)

Nothing has been refactored yet beyond the Sprint E0 structure itself. The
planned genuine refactoring is the Sprint E1/E2 extraction rework:
`app/services/extraction.py` becomes the pipeline orchestrator over a
pluggable extractor (GLM client + existing local parser fallback), which
will be documented here when implemented.

## Code review (§21)

A structured code review of the enhancement implementation is scheduled for
Sprint E6 (and after each sprint's gate); findings will be recorded here
verbatim, including any suggestions rejected and why.
