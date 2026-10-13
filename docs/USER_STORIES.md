# USER STORIES — Invoice Processing System Enhancement

Source of truth: the root `Invoice_Processing_Enhancement_Assignment.md`
(Sections 3–19 requirements, Section 24 acceptance criteria). This document
maps every major functional and non-functional requirement to a user story
in "As a …, I want …, so that …" format with testable acceptance criteria,
and reconciles coverage against all 21 acceptance criteria (Section 3).

**Status legend** (evidence-based; a story is Done only when implemented
AND its named tests were actually executed and recorded — code existence
alone is never sufficient):

- **Done (committed)** — implemented, tests executed and recorded, included
  in commit `b4bbee9` (Sprint E1) or `daeb9c2` (Sprint E0).
- **Done (tested, uncommitted)** — implemented and tests recorded in the
  working tree (full suite 280 passed, recorded in TEST_PLAN.md R-E2-4);
  commit pending authorization.
- **Partial** — some acceptance criteria met with recorded evidence; the
  rest are pending later-sprint work.
- **Planned** — not started; no tests exist for it.
- **Pending (blocked/awaiting input)** — implemented or specified, but a
  required input (e.g. the user's Z.ai API key for the live smoke) is not
  yet available.

**ID scheme:** enhancement stories `US-E<sprint>-<n>`; non-functional
stories `US-NFR-<n>`; the pre-enhancement baseline stories remain `US-1`
… `US-12` in the legacy section (Section 6). All IDs are unique.

**Dependencies** reference story IDs; where a dependency is satisfied by
Sprint E1's committed state it is marked "(met, E1)".

---

## 1. Epic ↔ assignment-requirement mapping

| Epic (sprint) | Assignment sections covered | Stories |
|---|---|---|
| E0 — foundations (migration, status machine, audit, config, docs) | §12, §13, §19/§20, §22 | US-E0-1..5 |
| E1 — asynchronous pipeline, retries, recovery, audit events, safe logging | §5, §12, §13, §15, §22 | US-E1-1..6 |
| E2 — GLM extraction (text + vision), JPG/JPEG/PNG uploads, response validation | §4, §6, §7, §15 | US-E2-1..4 |
| E3 — business validation, duplicate classification, extended invoice fields | §8, §9, §6 | US-E3-1..3 |
| E4 — approval routing, roles, approve/reject actions | §10, §11, §3 (roles) | US-E4-1..3 |
| E5 — invoice list/filter, detail panels, lifecycle polish | §14, §3.1 (visibility), §12/§13 (UI) | US-E5-1..4 |
| E6 — verification, documentation, live smoke, demonstration | §16, §19, §20, §21, §23, §24 | US-E6-1..6 |
| Non-functional posture (quality, secrets, offline tests, migration safety, bounded failures) | §15, §17, §22 | US-NFR-1..5 |

---

## 2. Enhancement user stories

### 2.1 Sprint E0 — foundations (all Done, committed `daeb9c2`)

**US-E0-1 (Done, committed `daeb9c2`) — Enhancement branch hygiene**
- **User story:** As a developer, I want the enhancement work isolated on
  the branch `enhancement/assignment`, created without disturbing
  pre-existing uncommitted changes, so that prior work is preserved and
  every commit stays reviewable.
- **Acceptance criteria:** (1) branch exists from `master@f69a193`;
  (2) pre-existing `docs/05-prompt-log.md` and
  `docs/14-execution-commands.md` remain exactly as before; (3) no
  reset/clean/stash used; (4) all later commits use explicit-path staging.
- **Priority:** Must. **Dependencies:** none.
- **Evidence:** git before/after records (TEST_PLAN.md, P-E-08); protected
  files verified unstaged at every subsequent log check.

**US-E0-2 (Done, committed `daeb9c2`) — Backward-compatible schema migration**
- **User story:** As the system, I want v1 databases upgraded in place —
  preserving invoice IDs, field values, timestamps, and line items — so
  that existing records survive the enhancement.
- **Acceptance criteria:** (1) migration versioned (`PRAGMA user_version`)
  and idempotent; (2) IDs, field values, timestamps, and line items
  preserved (asserted); (3) foreign-key integrity clean; (4) a copy of the
  real database rehearsed and verified before any live migration; (5) live
  DB never migrated without authorization.
- **Priority:** Must. **Dependencies:** none.
- **Evidence:** `tests/unit/test_migration.py` (TC-MIG-01..07, 09); verified
  copy rehearsal (TEST_PLAN R-E0-4); live DB never migrated.

**US-E0-3 (Done, committed `daeb9c2`) — Environment-based configuration**
- **User story:** As the system, I want AI-provider settings read from the
  environment, so that no API key is ever hard-coded, logged, or committed.
- **Acceptance criteria:** (1) `ZAI_*` settings env-driven with safe
  defaults; (2) no default contains key material; (3) `.env.example`
  placeholders only; (4) `.env` git-ignored.
- **Priority:** Must. **Dependencies:** none.
- **Evidence:** `tests/unit/test_config.py` (TC-CFG-*); `.gitignore`
  contains `.env`; repo grep shows no key material.

**US-E0-4 (Done, committed `daeb9c2`) — Status machine and audit foundation**
- **User story:** As the system, I want invoice status transitions enforced
  in exactly one place with an audit row written atomically per transition,
  so that the lifecycle is controlled and history is maintained.
- **Acceptance criteria:** (1) 8-state lifecycle; (2) every legal
  transition resolves; (3) ≥15 illegal pairs (incl. Approved→Approved,
  Approved→Rejected) raise `InvalidTransition`; (4) approval boundary
  < ₹1,00,000 → manager / ≥ → finance (unit-level; flow wiring is E4);
  (5) status + audit written in one transaction.
- **Priority:** Must. **Dependencies:** US-E0-2.
- **Evidence:** `tests/unit/test_workflow.py` (TC-SM-01..04,
  TC-APPR-ROUTE-01..04).

**US-E0-5 (Done, committed `daeb9c2`) — Canonical documentation skeletons**
- **User story:** As a reviewer, I want the exact Heading-20 documents
  present with accurate content and no fabricated results, so that
  documentation claims are trustworthy.
- **Acceptance criteria:** (1) the six canonical `docs/*.md` + root
  `CLAUDE_USAGE.md` exist; (2) only recorded results appear; (3) future
  work marked planned, not done.
- **Priority:** Must. **Dependencies:** none.
- **Evidence:** created in E0; updated since only with recorded results
  (E6 TC-DOC-CHECK re-verifies exhaustively).

### 2.2 Sprint E1 — asynchronous pipeline core (all Done, committed `b4bbee9`; suite 240 passed at commit)

**US-E1-1 (Done) — Asynchronous processing worker**
- **User story:** As a user, I want invoice processing to run in the
  background after upload, so that I do not wait for extraction to finish.
- **Acceptance criteria:** (1) upload returns before extraction starts
  (asserted); (2) `uploaded → processing → completed/failed` via the claim
  ladder; (3) serial single worker — no concurrent jobs per invoice;
  (4) extraction failures terminate exactly once with a safe message.
- **Priority:** Must. **Dependencies:** US-E0-2, US-E0-4 (met, E1).
- **Evidence:** TC-ASYNC-01, TC-PIPE-FAIL-01..03; recorded 240-passed run
  (TEST_PLAN R-E1-6/11).

**US-E1-2 (Done) — Non-blocking upload and live status**
- **User story:** As a user, I want the upload to return immediately and
  show live processing status, so that I can keep working while the
  background job runs.
- **Acceptance criteria:** (1) upload responds before processing starts
  (asserted); (2) `GET /invoices/<id>/status` reflects the transition;
  (3) the detail page is available for every status with polling;
  (4) unknown id → 404.
- **Priority:** Must. **Dependencies:** US-E1-1.
- **Evidence:** TC-ASYNC-02, TC-SM-05.

**US-E1-3 (Done) — Bounded retries and reprocessing**
- **User story:** As a user, I want transient extraction failures retried a
  bounded number of times and failed invoices reprocessable, so that
  temporary problems never permanently lose work.
- **Acceptance criteria:** (1) retryable failures re-attempt up to
  `WORKER_MAX_ATTEMPTS` per processing episode (M1: per-episode allowance;
  cumulative counter for observability only); (2) exhaustion → terminal
  `failed` exactly once; (3) `POST /invoices/<id>/reprocess` re-queues
  failed invoices (T5 audited atomically); (4) invalid reprocess requests
  refused with no audit write.
- **Priority:** Must. **Dependencies:** US-E1-1.
- **Evidence:** TC-PIPE-FAIL-02/03/06.

**US-E1-4 (Done) — Lifecycle audit events**
- **User story:** As an auditor, I want every lifecycle change recorded
  (what happened, to which invoice, when, and by whom), so that history is
  traceable end to end.
- **Acceptance criteria:** (1) invoice_uploaded,
  processing_started/resumed/completed/failed, extraction_completed/failed,
  and reprocess_requested are written at the defined points; (2) event
  sequences asserted for happy and failure paths; (3) exactly one terminal
  failure pair per episode (no audit spam).
- **Priority:** Must. **Dependencies:** US-E0-4.
- **Evidence:** event-sequence assertions in TC-ASYNC/TC-PIPE/TC-RECV.

**US-E1-5 (Done) — Safe errors and structured logging**
- **User story:** As a user, I want failures reported safely — no
  tracebacks, no leaked secrets — with errors logged for troubleshooting,
  so that I can understand what went wrong without sensitive data being
  exposed.
- **Acceptance criteria:** (1) DEBUG=False; (2) two structured loggers with
  a field allowlist (non-allowlisted fields raise); (3) sanitised
  tracebacks only; (4) generic 500 page with HTTPException pass-through;
  (5) the API key never appears in records, responses, or logs (asserted).
- **Priority:** Must. **Dependencies:** US-E0-3.
- **Evidence:** TC-ERR-500-01, TC-LOG-01/01b, TC-KEY-01; re-asserted in E2
  (TC-GLM key-leak test).

**US-E1-6 (Done) — Restart recovery with job ownership**
- **User story:** As the system, I want invoices left in `uploaded` or
  `processing` by a restart to be recovered exactly once, so that no work
  is silently lost or duplicated.
- **Acceptance criteria:** (1) recovery selects `uploaded`/`processing` and
  writes nothing itself; (2) only recovery-designated jobs resume
  `processing`; (3) no duplicate `processing_started`/`processing_resumed`
  audit rows; (4) enqueue dedupe prevents duplicate jobs.
- **Priority:** Must. **Dependencies:** US-E1-1.
- **Evidence:** TC-RECV-01..04.

### 2.3 Sprint E2 — GLM extraction, images, response validation (all Done — tested, uncommitted; commit pending authorization)

**US-E2-1 (Done — tested, uncommitted) — GLM extraction for text PDFs**
- **User story:** As a user, I want configured GLM extraction for
  text-layer PDF invoices, so that fields are extracted without the local
  rules parser.
- **Acceptance criteria:** (1) configured key + text PDF → text model with
  native JSON mode; (2) draft persisted in parser shape
  (`source:"glm"`, model in meta); (3) request carries the configured
  model, JSON mode, auth header, output cap (`ZAI_MAX_TOKENS`);
  (4) unconfigured → local parser fallback (decision 1); (5) request shape
  asserted (model, JSON mode, auth header, max_tokens).
- **Priority:** Must. **Dependencies:** US-E0-3, US-E1-1 (pipeline seam,
  met).
- **Evidence:** TC-GLM-TEXT-01 (mocked HTTP); fallback test
  TC-FALLBACK-01; R-E2-4.

**US-E2-2 (Done — tested, uncommitted) — Strict AI-response validation**
- **User story:** As the system, I want every AI response validated
  against the expected schema before use, so that malformed or hostile
  responses never corrupt invoice data.
- **Acceptance criteria:** (1) strict schema/type/date/amount/currency
  coercion — malformed values degrade to missing with a note, never stored
  raw; (2) code fences tolerated; (3) non-JSON / array-not-object /
  `line_items` not an array → schema error; (4) exactly one re-ask, then a
  typed permanent failure with the raw response retained size-capped
  (`RAW_RESPONSE_MAX_BYTES`); (5) unknown fields tolerated; (6) invalid
  line items skipped without breaking valid ones.
- **Priority:** Must. **Dependencies:** US-E2-1.
- **Evidence:** `tests/unit/test_glm_response.py` (TC-RESP unit set);
  TC-RAW-01 (truncation); malformed/re-ask integration test.

**US-E2-3 (Done — tested, uncommitted) — JPG/JPEG/PNG uploads and vision
extraction**
- **User story:** As a user, I want image invoices (JPG/JPEG/PNG) and
  scanned PDFs extracted via the vision model, so that I am not limited to
  text PDFs.
- **Acceptance criteria:** (1) gates accept `.jpg/.jpeg/.png` by content
  signature (JPEG `FF D8 FF`, PNG `89 50 4E 47`) and reject mismatches;
  (2) image uploads require GLM — unconfigured → clear permanent "not
  configured" message; (3) scanned PDFs rasterize at most
  `VISION_MAX_PAGES` (3) pages, each ≤5 MB / ≤6000 px (downscaled as
  needed); (4) originals served with correct MIME types; (5) the vision
  path calls `ZAI_VISION_MODEL` with base64 images (asserted).
- **Priority:** Must. **Dependencies:** US-E2-1, US-E1-3, US-E0-3.
- **Evidence:** TC-GLM-VISION-02, TC-GLM-SCAN-03, TC-FALLBACK-02/03, MIME
  assertions in tests/integration/test_glm_extraction.py.

**US-E2-4 (Pending — blocked on user input) — Live API smoke test**
- **User story:** As a developer, I want one real text PDF and one real
  image extracted through the configured GLM path, so that the integration
  is verified beyond mocks.
- **Acceptance criteria:** (1) performed with the user's real key and
  recorded in TEST_PLAN; (2) model names confirmed against the account;
  (3) no live call ever occurs in the automated suite.
- **Priority:** Should. **Dependencies:** US-E2-1..3; user-supplied key.
- **Evidence:** none yet — TEST_PLAN R-E2-3 records NOT PERFORMED; no
  live call has been made.

### 2.4 Sprint E3 — business validation, duplicates, extended fields (Planned — not started)

**US-E3-1 (Planned) — Business validation with verdicts**
- **User story:** As a user, I want every extracted invoice automatically
  validated after processing, so that invalid data cannot proceed silently
  and I can see exactly what is wrong.
- **Acceptance criteria (planned, per assignment §8.1–8.5):**
  1. Mandatory-field validation: invoice number, invoice date, vendor
     name, currency, and total amount must be present (§8.1).
  2. Amount validation: subtotal + tax = total, and the sum of line-item
     totals = subtotal, within a configurable tolerance (§8.2).
  3. Date validation: invoice date ≤ today, due date ≥ invoice date
     (§8.3).
  4. GSTIN format validation when present (§8.4).
  5. Result recorded as Passed / Warning / Failed with findings the user
     can understand (§8.5).
  6. ≥20 unit tests + integration test TC-VAL-INT-01.
- **Priority:** Must. **Dependencies:** US-E1-1, US-E2-1/2.

**US-E3-2 (Planned) — Duplicate classification with explanations**
- **User story:** As a user, I want probable duplicates detected,
  classified as No Duplicate / Possible Duplicate / Exact Duplicate, and
  explained with the matching records named, so that I can decide instead
  of guessing.
- **Acceptance criteria (planned):** (1) exact = vendor + invoice number;
  (2) possible = vendor + amount + date; (3) classification + explanation
  persisted (`dup_status`/`dup_matches`); (4) duplicates never block
  processing by themselves; (5) tests TC-DUP-*.
- **Priority:** Must. **Dependencies:** US-E1-1, US-E3-1.
- **Note:** the baseline duplicate *warning* (legacy AC-4.2) is preserved;
  E3 adds the §9 classification layer on top.

**US-E3-3 (Planned) — Extended invoice fields (§6)**
- **User story:** As a user, I want PO number, bill-to name and address,
  ship-to name and address, vendor GSTIN, and per-line tax extracted,
  validated, editable, and stored, so that Section 6 is fully covered.
- **Acceptance criteria (planned):** (1) fields present in the GLM
  prompt/schema and the local parser where extractable; (2) strict
  validation for each; (3) editable in the review form; (4) persisted
  (columns exist since E0); (5) prefill + persistence tests.
- **Priority:** Must. **Dependencies:** US-E2-1/2, US-E0-2 (columns exist).

### 2.5 Sprint E4 — approval workflow (Planned — not started)

**US-E4-1 (Partial) — Approval routing**
- **User story:** As the system, I want invoices routed by amount
  (< ₹1,00,000 → manager; ≥ ₹1,00,000 → finance) when they are submitted
  for approval, so that the right role acts.
- **Acceptance criteria:** (1) **met:** the routing rule is implemented and
  unit-tested at the ₹1,00,000 boundary (TC-APPR-ROUTE-01..04,
  `workflow.required_approver`); (2) **pending (E4):** routing wired into
  the submit flow with the `approval_assigned` audit event.
- **Priority:** Must. **Dependencies:** US-E3-1, US-E0-4 (met).

**US-E4-2 (Planned) — Role mechanism with documented limits**
- **User story:** As an approver, I want a session role so that approval
  actions are restricted to the matching role — documented honestly as a
  workflow mechanism, not authentication.
- **Acceptance criteria (planned):** TC-ROLE-01..14 (vendor and mismatched
  approver refused with no state change or audit write; queue filtered by
  role; limits documented).
- **Priority:** Must. **Dependencies:** US-E4-1.

**US-E4-3 (Planned) — Approve, reject, and rejection reason**
- **User story:** As an approver, I want to approve or reject a pending
  invoice — rejecting requires a reason — so that decisions are recorded
  and irreversible without a fresh submission.
- **Acceptance criteria (planned):** (1) only `pending_approval` is
  actionable; (2) role must match `approver_role`; (3) rejection reason
  mandatory, stored, and displayed; (4) T10/T11 audited;
  Approved→Approved/Rejected refused. Tests TC-APPR-ACT/REJ-*.
- **Priority:** Must. **Dependencies:** US-E4-1/2, US-E0-4.

### 2.6 Sprint E5 — views and lifecycle polish (Planned — not started)

**US-E5-1 (Planned) — Invoice list with status filter and ID column**
- **User story:** As a user, I want the invoice list to show all invoices
  with a status filter and the invoice ID, so that I can find and track
  any record.
- **Acceptance criteria (planned):** TC-LIST-* (filter by each status; ID
  column shown).
- **Priority:** Must. **Dependencies:** US-E1-2.

**US-E5-2 (Planned) — Detail panels and vendor visibility**
- **User story:** As a vendor, I want one detail page showing my invoice's
  processing status, extracted information (all Section 6 fields),
  validation errors/warnings, duplicate warnings, approval state, audit
  timeline, and final status, so that I always know exactly where it
  stands.
- **Acceptance criteria (planned):** TC-DETAIL-* covering every panel;
  raw response collapsed and escaped (TC-RAW-02 UI half moves here).
- **Priority:** Must. **Dependencies:** US-E3-1/2, US-E4-3, US-E1-4.

**US-E5-3 (Planned) — Delete policy and schema tightening**
- **User story:** As the system, I want deletion blocked while
  `processing` and the transitional status values removed once review/save
  is rewired, so that the lifecycle stays clean.
- **Acceptance criteria (planned):** delete-guard tests; v3 migration
  dropping the deprecated `extracted`/`saved` CHECK values with its own
  tests.
- **Priority:** Must. **Dependencies:** US-E1-1, US-E3-*, US-E4-*.

### 2.7 Sprint E6 — verification, documentation, demonstration (Planned — not started)

**US-E6-1 (Planned) — Full regression and negative-test inventory**
- **User story:** As a reviewer, I want the complete suite rerun and the
  §16 negative-test inventory (unsupported file, empty file, invalid
  invoice data, missing mandatory field, invalid GSTIN, wrong total,
  malformed AI response, extraction failure, duplicate, unauthorized
  approval, invalid status transition) all passing or explicitly
  scheduled, so that the release claim is evidenced.
- **Acceptance criteria (planned):** (1) full suite green at HEAD with
  counts recorded; (2) each §16 negative case has a named, passing test or
  an explicitly scheduled owner; (3) results recorded in TEST_PLAN.
- **Priority:** Must (assignment §16/§24).
- **Dependencies:** US-E1-1..6, US-E2-1..3, US-E3-1..3, US-E4-1..3.
- **Status/evidence:** none yet — planned.

**US-E6-2 (Planned) — Documentation finalisation**
- **User story:** As a reviewer, I want TEST_PLAN and KNOWN_ISSUES
  finalised with only recorded results, so that documentation claims stay
  auditable against executed evidence.
- **Acceptance criteria (planned):** (1) every documented claim has a
  matching recorded run or commit; (2) no fabricated results; (3)
  KNOWN_ISSUES entries carry status and mitigation.
- **Priority:** Must (assignment §19/§24).
- **Dependencies:** US-E6-1; the sprint entries P-E-15..P-E-26.
- **Status/evidence:** partial precursors exist (TEST_PLAN/KNOWN_ISSUES
  current through Sprint E2).

**US-E6-3 (Planned) — CLAUDE_USAGE.md completion**
- **User story:** As a reviewer, I want CLAUDE_USAGE.md completed with
  genuine evidence only (implementation, debugging, review cycles as they
  actually occurred), so that the Claude Code record remains trustworthy.
- **Acceptance criteria (planned):** (1) every §21-required section
  present (exploration, planning, implementation, ≥2 debugging cases,
  refactoring, code review); (2) no fabricated events.
- **Priority:** Must (assignment §21).
- **Dependencies:** the sprint interactions it records (P-E-15..P-E-26
  exist; later entries pending).
- **Status/evidence:** partial — genuine entries through Sprint E2
  (implementation bullet, debugging D-5..D-9); sections for later sprints
  marked pending.

**US-E6-4 (Planned) — End-to-end demonstration and walkthrough**
- **User story:** As a reviewer, I want a recorded functional
  demonstration (upload → processing → review → submit → approve; reject;
  duplicate; live smoke), the technical walkthrough (architecture, DB
  design, background processing, AI integration, error handling, testing
  approach, key decisions), and the Claude Code demonstration required by
  assignment §23, so that all three §23 demonstration areas are covered
  with recorded evidence.
- **Acceptance criteria (planned):** (1) the functional demo run recorded
  step by step; (2) the walkthrough covers all §23 technical topics;
  (3) the Claude Code demonstration covers exploration, planning,
  implementation, debugging, refactoring, and review.
- **Priority:** Must (assignment §23).
- **Dependencies:** US-E2-4 (live smoke), US-E3-*, US-E4-*, US-E5-*.
- **Status/evidence:** none yet — planned.

**US-E6-5 (Planned) — Traceability matrix completion**
- **User story:** As a reviewer, I want all 21 acceptance criteria
  evidenced with no unchecked claims, so that the final acceptance claim
  is fully supported.
- **Acceptance criteria (planned):** (1) every AC row names its story,
  test IDs, and recorded evidence; (2) no unchecked claims remain.
- **Priority:** Must (assignment §24).
- **Dependencies:** US-E6-1..4.
- **Status/evidence:** none yet — planned.

### 2.8 Non-functional stories

**US-NFR-1 (Done, committed `b4bbee9`) — Localhost-only single-user
posture**
- **User story:** As the system, I bind to 127.0.0.1 only and treat the
  app as single-user-localhost, so that exposure is minimised.
- **ACs:** binding + Origin-check tests; documented limits (role mechanism
  is not authentication; GLM path sends invoice content to the configured
  provider when configured — disclosed K-2/K-3).
- **Priority:** Must. **Dependencies:** none.

**US-NFR-2 (Done, committed `b4bbee9`) — Secret-safe configuration and
logging**
- **User story:** As the system, I keep the API key env-only and out of
  records, responses, and logs, so that no secret can leak through
  configuration, records, or logs.
- **ACs:** TC-CFG-*, TC-KEY-01, TC-LOG-01/01b, TC-GLM key-leak test.
- **Priority:** Must. **Dependencies:** US-E0-3.

**US-NFR-3 (Done, committed `b4bbee9`) — Offline deterministic test suite**
- **User story:** As a developer, I want the automated suite fully offline
  (HTTP mocked at one seam, temp databases, no API key), so that tests are
  deterministic, fast, and free.
- **ACs:** conftest temp-config design; `http_post_json` seam; recorded
  280-passed run (R-E2-4).
- **Priority:** Must. **Dependencies:** US-E2-1 (client seam).

**US-NFR-4 (Done, committed `b4bbee9`) — Migration safety rehearsal**
- **User story:** As the system, I require a verified copy-based rehearsal
  before any live migration, with the live database protected by
  authorization gates, so that no release claim rests on unverified
  migration code.
- **ACs:** TC-MIG-*; R-E0-4 rehearsal record; live DB never migrated.
- **Priority:** Must. **Dependencies:** US-E0-2.

**US-NFR-5 (Done, committed `b4bbee9`) — Bounded, classified failures**
- **User story:** As the system, I classify failures (retryable vs
  permanent vs transient DB lock) and bound every retry loop by
  configuration, so that no failure loops forever or silently drops work.
- **ACs:** M1 per-episode retries (TC-PIPE-FAIL-*), M2 DB-lock retries
  with exhaustion → boot recovery (TC-DBLOCK-01..04).
- **Priority:** Must. **Dependencies:** US-E1-3.

---

## 3. Acceptance-criteria coverage (assignment §24, 21 criteria)

| AC | Criterion (abridged) | Covered by | Status |
|---|---|---|---|
| 1 | Application enhanced | E0–E6 collectively | **Partial** — E0/E1 committed; E2 tested (uncommitted); E3–E6 pending |
| 2 | Required file types | US-E2-3 | **Done (tested, uncommitted)** — offline-tested; live vision path awaits smoke |
| 3 | Upload does not block | US-E1-2 | **PASS** (TC-ASYNC-01) |
| 4 | Processing status available | US-E1-2 | **PASS** (TC-ASYNC-02) |
| 5 | AI extraction structured | US-E2-1/2 | **Done (offline-tested)** — live smoke pending (US-E2-4) |
| 6 | Invalid AI responses handled | US-E2-2 | **Done (offline-tested)** |
| 7 | Extraction failures handled | US-E1-3 | **PASS** (TC-PIPE-FAIL-*) |
| 8 | Business validation | US-E3-1 | **Pending** (E3) |
| 9 | Duplicate classification | US-E3-2 | **Pending** (E3) |
| 10 | Approval routing | US-E4-1 | **Partial** (rule unit-tested; wiring E4) |
| 11 | Approve/reject actions | US-E4-3 | **Pending** (E4) |
| 12 | Rejection reason captured | US-E4-3 | **Pending** (E4) |
| 13 | Status transitions controlled | US-E0-4/US-E1-1 | **PASS** (TC-SM-*) |
| 14 | Audit history | US-E0-4/US-E1-4/US-E5-2 | **Partial** (events done; timeline UI E5) |
| 15 | List/detail/filtering | US-E5-1/2 | **Partial** (detail all-status done in E1; filter/panels E5) |
| 16 | Safe error handling & logging | US-E1-5 | **PASS** (TC-ERR/LOG/KEY/RAW) |
| 17 | Automated tests | all sprints | **PASS** — 280 passed (recorded) |
| 18 | SDLC documentation | US-E0-5/US-E6-2 | **Partial** (canonical docs current; E6 finalisation pending) |
| 19 | Claude Code usage documented | US-E6-3 | **Partial** (genuine entries through E2; ongoing) |
| 20 | Git practices | US-E0-1 + sprint discipline | **PASS** (explicit-path staging; E0/E1 commits) |
| 21 | End-to-end demonstration | US-E6-4 | **Not verified** (E6) |

**Known gaps:** AC-8, AC-9, AC-10/11/12 wiring, AC-14/15 UI halves, AC-21 —
all scheduled E3–E6. Extended §6 fields (PO/ship-to/per-line tax) land
with US-E3-3.

---

## 4. Legacy baseline stories (preserved verbatim — pre-enhancement app)

These are the original US-1..US-12 stories from docs/01-requirements-
analysis.md, preserved exactly as written, with their **original
priorities unchanged**. They describe the **pre-enhancement** application
and are **not** claimed to satisfy enhancement requirements on their own.
(Where the enhancement supersedes a baseline story, that is recorded as an
enhancement-level note, not a revision of the baseline.)

- **US-1 (Must) — Upload an invoice:** As a user, I want to upload an
  invoice file so the app can process it.
- **US-2 (Must) — Extract the details automatically:** As a user, I want
  the app to pull the invoice fields out of the file so I don't retype
  them.
- **US-3 (Must) — Review and correct before saving:** As a user, I want to
  check and fix the extracted values so wrong data never enters my
  records.
- **US-4 (Must) — Save a confirmed invoice:** As a user, I want to save
  the reviewed invoice to the database so it is permanently stored.
- **US-5 (Must) — See all stored invoices:** As a user, I want a list of
  saved invoices so I can find past ones.
- **US-6 (Must) — See one invoice in full:** As a user, I want a detail
  view of a stored invoice, including its original file, so I can verify
  it.
- **US-7 (Must) — Understandable failures:** As a user, I want a clear
  explanation when a file can't be processed so I know what to do next.
- **US-8 (Should) — Edit a stored invoice:** As a user, I want to correct
  a saved invoice so records stay accurate over time.
- **US-9 (Should) — Delete a stored invoice:** As a user, I want to remove
  a saved invoice and its file so my records stay clean.
- **US-10 (Should) — Find invoices quickly:** As a user, I want to search,
  filter, and sort the list so I can locate an invoice fast.
- **US-11 (Could) — Process scanned invoices:** As a user, I want scanned
  or photographed invoices to be extracted too, so I'm not limited to
  digital PDFs. *(Enhancement note: the E2 vision path now addresses
  scanned/image invoices; the baseline story is unchanged.)*
- **US-12 (Could) — Export to CSV:** As a user, I want to export my
  invoices so I can use them in a spreadsheet. *(Still out of scope.)*

Their original acceptance criteria (AC-1.1 … AC-12.1) remain in docs/01
§6 and are intentionally not duplicated here.
