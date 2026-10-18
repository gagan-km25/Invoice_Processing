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
- **Sprint E2 implementation (2026-10-13, genuine).** Claude Code
  implemented the GLM client (requests 2.34.2, pinned; text JSON-mode and
  vision base64 paths; transient/permanent classification), the
  provider-selection extraction flow with strict response validation, one
  re-ask, size-capped raw retention, and pypdfium2 rasterization (≤3
  pages), extended the upload gates to JPG/JPEG/PNG with content
  signatures, and added 30 offline tests (mocked HTTP only). Development
  was test-driven in small cycles; the suite caught four genuine defects
  during the build (recorded under Debugging below: D-5, D-6, D-7 and the
  PIL environment issue). Final recorded result: **275 passed** (240
  pre-E2 + 35 new). The live API smoke has NOT been performed — it awaits
  the user's Z.ai key and is recorded separately (TEST_PLAN R-E2-3).
- **Sprint E2 review-and-fix cycle (2026-10-13, genuine).** The code
  review confirmed M-A (rasterization errors escaping unclassified — now a
  safe permanent failure), M-B (no output cap — `ZAI_MAX_TOKENS`, default
  4000, asserted in request-shape tests), L-A (dead MIME dict removed),
  L-B (local-parser runs clear stale GLM raw responses), and L-C
  (transport catch narrowed to `requests.exceptions.RequestException`).
  While adding the M-B request-shape assertion, the review's stubs were
  exposed as masking **H-1: the vision path was calling the TEXT model**
  (`_glm_chat` hardcoded it); the model is now threaded through and
  asserted. Recorded runs: **40 focused / 280 full**, all green
  (TEST_PLAN R-E2-4).
- **Sprint E3 implementation (2026-10-13/14, genuine).** Claude Code
  implemented the §8 business-validation engine (`app/services/
  validation.py`, pure functions, Decimal arithmetic, inclusive
  configurable tolerance, injectable "today"), duplicate classification
  (`app/services/duplicates.py`), pipeline wiring (T2/T3 transitions),
  the §6 extended fields end-to-end (GLM schema + coercion, persistence,
  review form, detail panels), and the acceptance-evidence tests that the
  acceptance review demanded (TC-E3-XF-*). The suite caught two genuine
  defects during the build (D-10, D-11 below) and the implementation
  surfaced the discount-equation conflict resolved by decision record
  docs/15 (D-12). Accepted 2026-10-14 after a read-only acceptance audit.
- **Sprint E4 implementation (2026-10-14, genuine).** Claude Code
  implemented submission routing (one-transaction status + `approver_role`
  + two audit entries), approve/reject with mandatory stored rejection
  reasons, the session-role mechanism with the ARCHITECTURE §6 route-map
  guards (403 with zero database/audit writes on every wrong-role
  attempt — asserted directly against the database, not via HTTP codes),
  and the role-filtered approval queue. An editing mistake during the
  build (the `save_invoice` signature line clobbered by an insertion) was
  caught immediately by `py_compile` and repaired before proceeding.
  Accepted 2026-10-14.
- **Sprint E6 (2026-10-14/15, genuine).** Documentation finalisation
  (requirement inventory R-001…R-074 in REQUIREMENTS.md, §16 coverage map,
  §24 reconciliation, README rewrite, E6 accuracy checklist), the
  authorized isolated browser session investigation (three INR uploads:
  currency label unread, item-header vendor, zero line items — D-14),
  general-INR parser fixes (₹/Rs./Rs/INR amount tokens, Indian digit
  grouping, European/Indian comma-group disambiguation rule), the offline
  ISO 4217 currency dataset (currencies.py, 164 active codes with
  minor-unit exponents including zero-decimal JPY/KRW), split
  CGST/SGST/IGST tax summation with combined-row precedence, and the F1
  ambiguous-currency guard with regression tests TC-E6-C06..C09. Commit
  series executed per user authorization: 795e5bf (E3–E5), c197e11 (E6
  documentation), 2e9b85a (parser fix), b1cce06 (ISO 4217 + general INR
  fixes), f2cf019 (E6 docs close), 2b67d31 (reprocess visibility fix).
  Recorded progression: 414 → 421 → 428 →
  447 → 448, then +25 restored Sprint 2 normalize tests and the reprocess
  visibility regression → **473 passed**, parser suite **110 passed**, and
  after the reprocess template fix **474 passed / 0 failed**, then the
  final offline verification **478 passed / 0 failed** (2026-10-15) —
  recorded in TEST_PLAN. Live GLM
  smoke, browser-level verification and the §23 demonstration remain
  pending authorization. Also: docs/05-prompt-log.md was rebuilt (per team
  feedback) as a chronological verbatim prompt log with UTC timestamps from
  the retained session transcripts (207 prompts recovered; v1 planning
  prompts P-01–P-14 marked unavailable).
- **Sprint E5 implementation (2026-10-14, genuine).** Claude Code
  implemented the all-status list with status filter and ID/Created
  columns, the audit-timeline and escaped collapsed raw-response panels,
  the save-flow rewire (save keeps the lifecycle status — `saved`
  removed), the status-blind duplicate gate, the
  `uploaded`/`processing` deletion guards, and the v3 schema-tightening
  migration with copy-rehearsal source-preservation tests (TC-MIG-V3-00..06).
  A test-side parameter-ordering bug was caught by the suite and fixed
  (D-13). E5 closed at **414 passed / 0 failed**; the live database is
  still v2 and upgrades only at the next authorised boot.

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

### D-5 — GLM provider errors became generic terminal failures (Sprint E2, 2026-10-13)

- **Problem:** With a persistently failing provider stub, the invoice went
  `failed` after exactly **one** attempt instead of the configured three,
  with a generic message.
- **Investigation:** `_run_pipeline`'s generic `except Exception` was
  converting the client's `GlmTransient` (raised by `post_chat`) into a
  sanitised `PipelineError` — the pipeline's retry allowance never saw it.
- **Root cause:** Client exceptions were never mapped to extraction's typed
  failure classes.
- **Solution:** `_glm_chat` catches `GlmTransient`/`GlmPermanent` and
  re-raises them as `ExtractionRetryable`/`ExtractionPermanent` (user-safe
  messages, cause suppressed). The pipeline's per-episode retry allowance
  and terminal handling then apply unchanged.
- **Testing:** TC-GLM-UNAVAIL-01 (exhaustion at the bound, HTTP-status
  message) and the retry-then-success test.

### D-6 — insert_invoice placeholder/column mismatch (Sprint E2, 2026-10-13)

- **Problem:** Every upload returned HTTP 500 with
  `sqlite3.OperationalError: 9 values for 8 columns` as soon as
  `insert_invoice` gained the `file_type` column.
- **Investigation:** Called `store_upload` directly under an app context
  with the exception propagated — the traceback pointed at the INSERT in
  [app/db/repository.py](app/db/repository.py).
- **Root cause:** The edit added the `file_type` column and its value but
  left one placeholder too many in the VALUES tuple.
- **Solution:** Placeholder count corrected to 8; a diagnostic harness
  (temp-configured app, direct service call) was used because the sanitised
  500 handler intentionally hides tracebacks.
- **Testing:** All upload-path tests pass; the suite's image-gate cases
  exercise the fixed statement.

### D-7 — GLM currency not normalized (Sprint E2, 2026-10-13)

- **Problem:** `test_valid_response_builds_parser_shaped_draft` failed:
  GLM `"currency": "usd"` produced draft value `'usd'` where the local
  parser normalizes to `'USD'`.
- **Investigation:** Compared the validator's currency branch with the
  parser's — the 3-letter check existed but no case normalization.
- **Root cause:** Lowercase model output passed the length check unchanged.
- **Solution:** `ai_json_to_draft` upper-cases a valid 3-letter currency.
- **Testing:** Unit test now asserts `USD`; full suite 275 passed.

### D-8 — Re-ask call omitted the model argument (Sprint E2, 2026-10-13)

- **Problem:** A malformed GLM response produced the GENERIC failure
  message (`worker_error error_class=TypeError`) instead of the typed
  invalid-response failure.
- **Investigation:** The traceback (captured via a direct
  `_glm_extract_with_reask` repro) showed
  `TypeError: _glm_chat() missing 1 required keyword-only argument: 'model'`
  on the **re-ask** call — the first call passed `model=`, the re-ask did
  not, so the re-ask raised `TypeError`, which the pipeline's sanitiser
  converted into a generic terminal failure.
- **Root cause:** `_glm_chat` gained a required `model` keyword when the
  vision/text models were threaded through (H-1); the re-ask call site was
  missed.
- **Solution:** The re-ask call passes `model=model`.
- **Testing:** TC-RESP-01/02 (re-ask then typed permanent) pass; the
  worker_error no longer appears for this path.

### D-9 — pdfium rejected the test-factory PDFs (Sprint E2, 2026-10-13)

- **Problem:** Scanned-PDF rasterization tests failed with
  `PdfiumError: Failed to load page.` although pdfplumber parsed the same
  bytes fine.
- **Investigation:** pdfium is stricter about stream `/Length`: the test
  factory emitted `/Length 0` for empty content streams while actually
  writing a 1-byte newline as stream data.
- **Root cause:** Off-by-one between the declared and actual stream length
  in the test-factory PDF syntax.
- **Solution:** `tests/conftest.py` now writes exact `/Length` with no
  padding newline before `endstream`.
- **Testing:** Scan-rasterize tests pass; pdfplumber-based tests unaffected.

### D-10 — Discounted invoices failed the literal amount equation (Sprint E3, 2026-10-13)

- **Problem:** With the E3 validation engine live, four of the five real
  sample invoices (docs/07 samples 2–5) became `validation_failed` — each
  off by exactly its discount — while the exploration doc said the
  consistency math was "verified exact on all five".
- **Investigation:** Recomputed both candidate equations with Decimal for
  all five documented samples: `subtotal + tax` failed by exactly the
  discount on every discounted invoice; `subtotal − discount + tax`
  matched all five exactly (docs/07 finding 5 also records
  `tax = (subtotal − discount) × rate`). The conflict was between the
  assignment's literal §8.2 equation and the project's own Phase-A data.
- **Root cause:** The approved severity mapping ("primary equation
  mismatch → Error; discount-aware mismatch → Warning") had been
  implemented as two independent always-on checks; the literal primary
  check cannot hold for a correctly issued discounted invoice.
- **Solution:** Applicable-equation model (decision record
  docs/15 D-E3-01, user-approved): with discount absent/zero validate
  `subtotal + tax = total` (Error); with discount non-zero validate
  `subtotal − discount + tax = total` (Warning, never blocking). No
  application change was made until the user approved the interpretation.
- **Testing:** New unit tests pin both branches and the boundary
  semantics (inclusive tolerance, no premature quantization); all five
  real samples validate `passed` end-to-end (TC-S2-E01..E05).

### D-11 — Non-numeric per-line tax was silently dropped (Sprint E3, 2026-10-13)

- **Problem:** The E3 acceptance-evidence tests (written to prove US-E3-3)
  failed: `TC-E3-XF-06/I05` expected a non-numeric `tax_{i}` to block the
  save with a named field error, but the record saved anyway.
- **Investigation:** `review.py::_validate_lines` computed
  `line_tax = parse_amount(...)` without a `None` check — an unparseable
  value became `None` and was stored, while every other decimal field
  (quantity, unit price, amount, header amounts) blocks with a named
  error per the Sprint 3 rule (AC-04.2).
- **Root cause:** The per-line tax field was new in E3 and its guard was
  omitted; the silent-drop path was never covered by a test until the
  acceptance-evidence suite was added.
- **Solution:** Stopped before fixing (user process): reported the defect
  with the two red tests as evidence; on approval, added the 4-line
  guard consistent with the sibling checks.
- **Testing:** TC-E3-XF-06 and TC-E3-XF-I05 went red → green; full suite
  357 passed at E3 close.

### D-12 — E5 list query mixed placeholder order (Sprint E5, 2026-10-14)

- **Problem:** `test_count_matches_listing` failed for the combined
  status + search filter (`status='failed', q='beta'` returned 0).
- **Investigation:** `list_invoices`/`count_invoices` appended the status
  parameter *after* the search parameters, while the SQL placed the
  `status = ?` placeholder *before* the search fragment — the values were
  swapped.
- **Root cause:** Parameter list and placeholder order were built in two
  different orders.
- **Solution:** The status value is now prepended so it matches the
  placeholder position; a combined-filter test pins the ordering.
- **Testing:** `test_history_repository.py` 14/14; full suite 414/0.

### D-13 — `save_invoice` signature clobbered mid-edit (Sprint E4, 2026-10-14)

- **Problem:** Inserting the three new E4 repository functions consumed
  the `def save_invoice(` line, leaving an orphaned parameter list —
  `py_compile` failed with `unmatched ')'`.
- **Investigation:** Compile check immediately after the edit localised
  the damage; the function inventory grep showed `save_invoice` missing.
- **Root cause:** An Edit whose `old_string` matched the function's
  signature line but whose replacement did not re-include it.
- **Solution:** Re-inserted the signature; compile + function inventory
  verified before any further work.
- **Testing:** Full suite green at E4 close (397/0).

## Refactoring (§21 requires at least one genuine area)

Genuine refactorings performed with Claude Code, beyond the Sprint E0/E1
structure:

- **Sprint E5 — lifecycle rewire and `saved` removal.** Review/save was
  rewired so saving persists the confirmed values while the record keeps
  its lifecycle status (`completed`); the transitional `saved` status was
  removed end-to-end (save-flow, duplicate gate, history, delete policy,
  and finally the schema CHECK via the v3 migration). All Sprint 3/4
  saved-flow tests were deliberately redefined; the duplicate gate became
  status-blind with self-exclusion; deletion moved from saved-only to
  blocked-only-while-`uploaded`/`processing`.
- **Sprint E3 — SQL moved back behind the repository seam.** The
  duplicate classifier originally executed its candidate query inline;
  the "all SQL lives in the repository" architecture rule was restored by
  routing it through `repository.find_duplicate_candidates`.
- **Sprint E4 — approval writes consolidated.** Submission and decisions
  each write status + columns + audit entries in ONE transaction through
  dedicated repository functions instead of ad-hoc multi-statement
  sequences, mirroring the `transition_status` pattern.

## Code review (§21)

Structured read-only acceptance reviews were performed and their findings
acted on after each sprint gate (all recorded in this file, TEST_PLAN and
the sprint plan):

- **E3 acceptance audit:** found the missing direct US-E3-3 persistence/
  prefill evidence (closed with the TC-E3-XF suite), the dangling
  "verification section below" reference and wording nits in docs/15
  (fixed), and the line-tax defect D-11 (found by tests, fixed on
  approval).
- **E4 acceptance audit:** verified zero-write refusal proofs at
  database level; found the E4 row's trailing empty table cell in
  SPRINT_PLAN.md (cosmetic, still open) and confirmed the protected
  documents' evidence chain (docs/14 provable only by mtime — stated
  explicitly rather than claimed).
- **E5 acceptance audit:** confirmed the migration's transaction/
  rollback/fk-gate discipline by code and by disposable-copy tests; the
  audit re-ran the full suite independently rather than trusting the
  recorded count.
- Rejected suggestions and why: refusing only `processing` from deletion
  was extended to `uploaded` as well — but only as a user-approved
  decision, not unilaterally; a stricter Error threshold for large
  discount-aware deviations was declined as out-of-scope without a new
  decision (docs/15 §5).


### D-14 — CPS-INV-5099 extracted zero line items; currency/vendor mis-extracted (E6 close, 2026-10-14)

- **Problem:** During the authorized isolated browser session, three
  uploaded invoices (CPS-INV-5099, BE-INV-2045, MOS-INV-3088) all showed
  vendor `Description`, no currency, and `validation_failed`
  (E_MISSING_CURRENCY); CPS-INV-5099 additionally had zero line items
  despite five item rows in the PDF.
- **Investigation:** Read-only dump of the isolated session database plus a
  read-only pdfplumber extraction of the stored upload. Currency: the local
  parser derives currency only from amount-attached glyphs + GST inference
  (fields.py) and never reads a `Currency: INR` label; the CPS amounts are
  plain numbers, so currency went `missing` (validation then correctly
  raised E_MISSING_CURRENCY). Vendor: `extract_vendor_block` accepted the
  first table's leading cell `Description` because the non-vendor guard did
  not know the item-table header keywords. Line items: pdfplumber's table
  HAS the header row (`Description/Qty/Unit Price/Amount`), but the item
  rows are name-first four-column `[description, qty, unit price, amount]`
  with no line number — `find_item_table` matched the header, yet
  `extract_line_items` required integer-leading 5-cell rows and dropped
  every row (E-15).
- **Root cause:** Three local-parser gaps for this layout family, all in
  extraction (the validation engine was faithful at every step).
- **Solution:** (1) explicit currency label rule with deterministic
  precedence (label > symbol > GST inference; garbled labels → ambiguous,
  never guessed); (2) item-table header keywords added to the non-vendor
  guard; (3) a name-first four-column row branch in the header path plus a
  headerless-fallback extractor requiring ≥2 item rows (never fabricating).
- **Testing:** TC-E6-F01..F07, TC-E6-L01..L06, TC-MIG unchanged; real-PDF
  re-parse of the stored upload produced currency `found INR`, vendor
  `CloudPeak Systems` (ambiguous), 5 line items with exact values, verdict
  `passed` (line-sum rule now satisfied). Full suite 421 → 428 passed.
  Currency/vendor fixes committed as 2e9b85a; the line-item fix is
  implemented, tested and committed as part of 795e5bf. The isolated
  session's stored rows were intentionally left as evidence (reprocessing
  through the UI applies the fix).


### D-15 — E6 test additions overwrote the Sprint 2 normalize suite (E6 close, 2026-10-15)

- **Problem:** The general-INR regression tests were written to
  `tests/unit/parser/test_normalize.py` with a Write that **replaced** the
  existing file — 25 Sprint 2 tests (TC-S2-N01…N27: dates, amounts,
  resolve_currency, invoice numbers, clean) were lost. The full suite still
  passed (448/0) because the lost tests covered still-working code.
- **Investigation:** The E6 pre-commit review enumerated 25 test functions
  at HEAD versus 4 in the working tree (`git show
  HEAD:tests/unit/parser/test_normalize.py`), and after the merge verified
  the restored test segment was byte-identical to HEAD (31/31 assert lines).
- **Root cause:** Wrote a new file without checking whether the path
  already existed.
- **Solution:** Merged — the HEAD file restored verbatim, the E6 tests
  appended, and the pytest parametrize decorator re-attached.
- **Testing:** `pytest tests/unit/parser/test_normalize.py -q` → 47 passed
  (25 restored + 4 E6, one parametrized ×9); parser directory 110; full
  suite 473, later 474 with the reprocess visibility regression.
