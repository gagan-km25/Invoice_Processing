# CLAUDE_USAGE — Invoice Processing System Enhancement

How Claude Code was used on the enhancement assignment, with only genuine
events. This file grows sprint by sprint; sections for work that has not
happened yet say so explicitly rather than containing invented material.
The complete chronological prompt record lives in **Part II of
[docs/05-prompt-log.md](docs/05-prompt-log.md)** (entries P-E-01 onward,
exact prompt texts preserved); this document cross-references it instead of
duplicating it. The pre-enhancement build's prompt history is Part I of the
same file (see also docs/13-evaluation-q-and-a.md).

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
- **Sprint E1 (2026-10-12).** Claude Code implemented the async processing
  pipeline (`app/services/pipeline.py`: single serial worker, job kinds,
  enqueue dedupe, claim ladder with recovery-job ownership, bounded
  retries, sanitised error containment, boot recovery), refactored
  `extraction.py` to the planned pluggable core (status ownership moved to
  the pipeline; typed retryable/permanent failures), added the structured
  two-logger `applog` with a structural field allowlist, the status
  endpoint, reprocess route, DEBUG=False and a generic 500 — plus 15 new
  tests, migrating legacy HTTP tests to drive the worker. Test reality:
  first run had a collection error, then 1/14, 13/2, 14/1 before 15/15;
  full suite needed four more honest fix-and-rerun cycles (30 → 7 → 4 → 1
  failed) before **235 passed**. All failures and fixes are recorded in
  docs/TEST_PLAN.md R-E1-1..R-E1-6.
- **Sprint E1 incident (honest record).** A production-boot verification
  imported `run.py` (module-level `create_app()`), which ran `init_db()` on
  the live database and migrated it to v2 without authorization
  (docs/TEST_PLAN.md R-E1-8, docs/KNOWN_ISSUES.md K-9). Content is
  lossless and the identical operation had passed the copy rehearsal, but
  the safeguard was breached; a restoration script is drafted and awaits
  the user's decision. Lesson: never import `run.py` for verification —
  always boot against a temp-configured app.
- **Sprint E1 review-and-fix cycle (2026-10-12/13, genuine).** The code
  review returned two confirmed Medium findings; both were fixed and
  verified with focused tests on temporary databases — no live runtime
  testing was performed. **M1:** the persisted retry counter was reused
  across separate manual reprocess episodes, so a spent episode shortened
  later retries; `_run_pipeline` now bounds retries per processing episode
  while `extract_attempts` accumulates lifetime attempts for observability
  (TC-PIPE-FAIL-07: an exhausted episode followed by a manual reprocess
  receives the full allowance again). **M2:** a transient SQLite lock
  during claiming or persistence consumed the queue job with no retry —
  and a lock during draft persistence was even converted into a generic
  terminal failure; `process_job` now retries lock/busy errors within
  `WORKER_DB_MAX_ATTEMPTS`, resumes the pipeline directly after a
  successful claim via a `claimed` flag (no duplicate audit), passes
  database errors past the sanitising handler, and leaves the row eligible
  for documented boot recovery on exhaustion (TC-DBLOCK-01..04). Recorded
  runs: M1 — 16 focused / 236 full; M2 — 20 focused / 240 full
  (docs/TEST_PLAN.md R-E1-10/11). Full M2 analysis and evidence:
  prompt log P-E-10/P-E-11.

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

### D-2 — Generic 500 handler swallowed 404s (Sprint E1, 2026-10-12)

- **Problem:** After adding `@app.errorhandler(Exception)`, tests failed
  with `assert 500 == 404`: unknown-invoice requests returned 500.
- **Investigation:** The captured log showed
  `event=unhandled_error error_class=NotFound` — Flask routes
  `HTTPException` to `errorhandler(Exception)` handlers (contrary to my
  assumption that it only receives non-HTTP exceptions).
- **Root cause:** The handler did not distinguish HTTP exceptions.
- **Solution:** Pass `HTTPException` instances through unchanged
  (`return error`) so Flask's normal 404/405 handling applies; only
  non-HTTP exceptions get the generic 500 page.
- **Testing:** TC-ASYNC-02 and the hardening suite's 404/405 cases pass;
  TC-ERR-500-01 verifies genuine exceptions still produce the generic page.

### D-3 — Worker ran outside the Flask app context (Sprint E1, 2026-10-12)

- **Problem:** 14 of the new pipeline tests errored with "Working outside
  of application context" — `get_db()` uses `current_app`.
- **Investigation:** The worker thread and boot-time recovery called
  repository code without pushing a context; tests call
  `run_pending()`/`process_job()` directly, so fixture-level contexts did
  not cover them.
- **Root cause:** Context ownership was implicit instead of belonging to
  the job itself.
- **Solution:** `process_job` (and `recover_stalled`) push their own
  `self.app.app_context()` — uniform for the thread loop, `run_pending`,
  and direct test calls, exactly as the approved design specified.
- **Testing:** All 15 pipeline tests pass; the production boot check
  confirms the thread runs jobs correctly.

### D-4 — Reprocess jobs were silently skipped (Sprint E1, 2026-10-12)

- **Problem:** After reprocessing a failed invoice, the record stayed
  `failed`; the events log showed
  `event=job_skipped job_kind=reprocess reason=status_failed`.
- **Investigation:** The claim ladder claimed `uploaded` and resumed
  `processing`, but never claimed `failed` rows — the reprocess job had no
  ladder rule, and the route was also writing the `reprocess_requested`
  audit outside the status transaction.
- **Root cause:** Ladder designed only around the upload/recovery paths.
- **Solution:** `failed`/`validation_failed` rows are claimable only by
  `reprocess` jobs, which perform T5/T5b via `apply_transition` — the
  `reprocess_requested` audit is now written in the same transaction as the
  status change (route only guards + enqueues).
- **Testing:** TC-PIPE-FAIL-06 asserts the full reprocess lifecycle, the
  single audited T5, and refusal paths with no audit writes.

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
