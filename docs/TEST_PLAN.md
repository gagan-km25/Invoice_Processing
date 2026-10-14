# TEST PLAN — Invoice Processing System Enhancement

Strategy: pytest, temporary databases only (conftest `tmp_path`), GLM client
stubbed in all automated tests — the network is touched only by recorded
manual smoke runs. Every result below is from an actually executed run;
nothing is pre-recorded for future sprints.

## 1. Recorded runs (actual executions)

| Run | Date | Command | Result |
|---|---|---|---|
| R-E0-1 | 2026-10-12 | `venv\Scripts\python -m pytest tests/unit/test_workflow.py tests/unit/test_migration.py tests/unit/test_config.py -q` (first run) | **2 failed, 49 passed** — failures recorded honestly: (a) migration omitted v1 indexes `idx_invoices_hash`/`idx_invoices_number` (caught by TC-MIG-09); (b) TC-MIG-02 wrongly asserted `status` byte-preservation. Both fixed; see R-E0-2 |
| R-E0-2 | 2026-10-12 | same, after fixes | **51 passed** |
| R-E0-3 | 2026-10-12 | `venv\Scripts\python -m pytest -q` (full suite) | **220 passed** (169 legacy + 51 new), 0 failed, ~15.75 s |
| R-E0-4 | 2026-10-12 | Migration rehearsal on a backup-API copy of the live `data/invoices.db` (original opened read-only twice, never written) | **PASS** — 11 invoices preserved (10 `saved`→`completed`, 1 `failed`), 0 lines preserved, `max_id`=12 preserved incl. pre-existing id gap, 11 `record_migrated` audit rows, `foreign_key_check` clean, `user_version` 0→2 on the copy, original still version 0 with 11 invoices |
| R-E1-1 | 2026-10-12 | new E1 tests, first run | **collection error** — `EVENT_PROCESSING_FAILED` missing from the audit catalogue; constant added |
| R-E1-2 | 2026-10-12 | new E1 tests | **1 passed, 14 errors** — worker/recovery ran outside an app context (`get_db` → RuntimeError); fixed: `process_job`/`recover_stalled` push their own app context |
| R-E1-3 | 2026-10-12 | new E1 tests | **13 passed, 2 failed** — the generic `errorhandler(Exception)` swallowed `HTTPException` (404s became 500s); fixed with an HTTPException pass-through |
| R-E1-4 | 2026-10-12 | new E1 tests | **14 passed, 1 failed** — reprocess jobs were skipped by the claim ladder (`status_failed`); added the `failed`/`validation_failed`→reprocess claim and moved the `reprocess_requested` audit into the T5 transition (atomic with the status change) |
| R-E1-5 | 2026-10-12 | new E1 tests | **15 passed** |
| R-E1-6 | 2026-10-12 | full suite, iterative | **30 failed** (legacy HTTP flows: upload no longer extracts in-request) → legacy test helpers/tests migrated to drive the worker → intermediate runs 7 → 4 → 1 failed → **235 passed** (final), 0 failed, ~52 s |
| R-E1-7 | 2026-10-12 | production boot verification (in-process `create_app` with real config) | worker thread alive; 0 recovery jobs on live DB (all rows terminal); `data/logs/events.log`+`errors.log` created. **INCIDENT recorded — see R-E1-8** |
| R-E1-8 | 2026-10-12 | incident | Importing `run.py` (module-level `create_app()`) executed `init_db()` on the **live** database and **migrated it to v2 without authorization** (no pre-migration backup taken). Content verified lossless (`legacy_status` preserves every original status; v1 columns untouched — same operation that passed R-E0-4 on a copy of this DB). No processing ran. A drafted restoration script returns the DB to the exact v1 state; **execution awaits the user's decision** — live-DB changes require explicit authorization |
| R-E1-9 | 2026-10-12 | **Incident resolution (user decision: Option B — retain schema v2)** | Verified backup created **before** any other action: `data/invoices-v2-backup-20261012-233018.db` (77,824 bytes) via SQLite's backup API from a `mode=ro` source connection. Independent verification **PASS**: 11 invoices; IDs `[1,2,3,4,5,7,8,9,10,11,12]` (pre-existing gap at id 6 preserved); statuses `completed`×10 (all legacy `saved`) + `failed`×1 (legacy `failed`); `user_version`=2; `foreign_key_check` clean; `integrity_check` ok; 11 `record_migrated` audit rows; **full logical equality with the source** (rows, schema, version). Source confirmed unchanged (pre/post snapshots identical on the read-only connection). Two earlier verification-script runs reported FAIL due to bugs in the verification script itself (v1-era positional column indexes; wrong expected ID gap) — the backup data was correct throughout; re-verified with named columns. Live DB retained at v2; no migration or restoration re-run |
| R-E1-10 | 2026-10-13 | review-fix **M1** (per-episode retry allowance): `pytest tests/integration/test_async_pipeline.py -q` then `pytest -q` | **16 passed** focused (incl. new TC-PIPE-FAIL-07 — exhausted episode followed by a manual reprocess receives the full allowance again); full suite **236 passed**, 0 failed |
| R-E1-11 | 2026-10-13 | review-fix **M2** (bounded transient DB-lock retries): `pytest tests/integration/test_async_pipeline.py -q` then `pytest -q` | **20 passed** focused (incl. new TC-DBLOCK-01..04 — lock retried to success; exhaustion leaves `processing` for boot recovery; non-lock errors not retried; claim lock without duplicate T1); full suite **240 passed**, 0 failed |
| R-E2-1 | 2026-10-13 | new E2 tests, iterative development runs (exact failure sequence recorded in the prompt log P-E-17): placeholder-count bug in `insert_invoice`, missing `Path` import, unmapped provider errors, currency normalization | Final E2 test files: `tests/unit/test_glm_client.py` (10), `tests/unit/test_glm_response.py` (10), `tests/integration/test_glm_extraction.py` (10) — **30 passed** after fixes |
| R-E2-2 | 2026-10-13 | `pytest -q` (full suite) | **275 passed**, 0 failed (~26 s) — 240 pre-E2 + 35 new |
| R-E2-4 | 2026-10-13 | code-review fixes **M-A/M-B/L-A/L-B/L-C** (+ H-1 vision-model threading found during M-B): focused `pytest tests/unit/test_glm_client.py tests/unit/test_glm_response.py tests/integration/test_glm_extraction.py -q` then `pytest -q` | **40 passed** focused (incl. new: max_tokens request-shape, non-RequestException not transient, rasterize failure → safe permanent, stale-raw cleared by local fallback, vision path calls `ZAI_VISION_MODEL`); full suite **280 passed**, 0 failed |
| R-E2-3 | — | Live API smoke (text PDF + image, real key) | **NOT YET PERFORMED** — requires the user's Z.ai API key and explicit go-ahead; recorded here only when actually run |

## 2. Sprint E0 test catalogue (executed)

| ID | Test | Verdict |
|---|---|---|
| TC-SM-01 | every legal transition resolves to its target (parametrized over TRANSITIONS) | PASS |
| TC-SM-02 | terminal states have no outgoing transitions | PASS |
| TC-SM-03 | 15 illegal transitions have no target (incl. Approved→Approved, Approved→Rejected) | PASS |
| TC-SM-04 | `apply_transition` writes status + audit atomically; refuses illegal pairs and unknown invoices; full lifecycle walk; validation_failed submit + reprocess paths | PASS |
| TC-APPR-ROUTE-01..03 | threshold boundaries 0/1/99999.99 → manager; 100000.00/100000.01/huge → finance | PASS |
| TC-APPR-ROUTE-04 | custom threshold override | PASS |
| TC-CFG-* | env overrides; no default key material; `.env.example` placeholders; `.env` git-ignored; 8 statuses; threshold/tolerance values | PASS |
| TC-MIG-01 | invoice IDs preserved; AUTOINCREMENT continues at max+1 | PASS |
| TC-MIG-02 | all v1 column values preserved (status via `legacy_status`) | PASS |
| TC-MIG-03 | timestamps byte-identical | PASS |
| TC-MIG-04 | line items preserved; `line_tax` NULL | PASS |
| TC-MIG-05 | `foreign_key_check` clean; cascade delete still works | PASS |
| TC-MIG-06 | idempotency: repeated boots change nothing (data, audit count, version) | PASS |
| TC-MIG-07 | status mapping, `legacy_status`, one `record_migrated` row per invoice | PASS |
| TC-MIG-09 | migrated schema == fresh schema (columns + indexes) | PASS |
| (guard) | `init_db` refuses a database claiming v2 without the v2 shape | PASS |

## 2b. Sprint E1 test catalogue (executed)

| ID | Test | Verdict |
|---|---|---|
| TC-ASYNC-01 | upload responds before processing; record still `uploaded` after response; worker completes it; exact audit sequence [invoice_uploaded, processing_started, extraction_completed, processing_completed] | PASS |
| TC-ASYNC-02 | JSON status endpoint tracks uploaded→completed; 404 unknown | PASS |
| TC-SM-05 | completed records are reviewable; `uploaded` records are not (guard message) | PASS |
| TC-PIPE-FAIL-01 | permanent failure (scan gate): terminal `failed`, user-safe reason, attempts=1, exact audit sequence with single [extraction_failed, processing_failed] pair | PASS |
| TC-PIPE-FAIL-02 | retryable failure then success: attempts=2, no extraction_failed event on ultimate success | PASS |
| TC-PIPE-FAIL-03 | retry exhaustion: attempts == WORKER_MAX_ATTEMPTS, exactly one terminal audit pair | PASS |
| TC-PIPE-FAIL-05 | unexpected exception → generic terminal message; exception sentinel absent from record, events log, errors log; errors log carries sanitised traceback only | PASS |
| TC-PIPE-FAIL-06 | reprocess after failure: T5 audited atomically (`reprocess_requested` ×1), completes; illegal reprocess refused with no audit, unknown id → 404 | PASS |
| TC-RECV-01 | `uploaded`-stalled recovery: processing_started ×1, no resume event, recovery writes no audit rows | PASS |
| TC-RECV-02 | `processing`-stalled recovery: processing_started still ×1, processing_resumed ×1, single completion set | PASS |
| TC-RECV-03 | ownership: normal job skips `processing` (no events); recovery job resumes | PASS |
| TC-RECV-04 | duplicate enqueue no-op (any kind); stale recovery job on terminal row skips with no events; healthy boot enqueues nothing | PASS |
| TC-ERR-500-01 | unhandled error → generic 500 page; sentinel absent from response and both logs; no Traceback in errors log | PASS |
| TC-LOG-01 | pipeline run leaves no invoice content in either log; events are structured | PASS |
| TC-LOG-01b | `log_event` refuses non-allowlisted fields (structural guarantee) | PASS |

## 3. Planned catalogue (NOT yet run — listed for traceability, no results claimed)

- **E2 live smoke (manual, pending user key):** one real text PDF and one
  real image through the configured GLM path; model names confirmed against
  the account; results recorded here.
- **E6:** full regression, TC-MIG-08 final rehearsal record, TC-DOC-CHECK,
  end-to-end demo dry run (manual, recorded).

Sprint E5 is now executed: all-status list with exact-status filter,
search composition, ID + Created columns (TC-LIST-01..05,
`tests/integration/test_e5_views.py`), audit-timeline + escaped collapsed
raw-response panels with role visibility (TC-DETAIL-01..04, TC-RAW-02 UI
half, same file), the rewired save flow and duplicate gate
(TC-S3-I12/I14/I17/I19 redefined in `test_review_save_flow.py`), the
deletion guards with zero-write refusals (TC-S4-I22 redefined +
TC-S4-U12, `test_history_delete_flow.py` / `test_history_repository.py`),
and the v3 tightening migration on disposable copies only — including the
copy-rehearsal proof that the source bytes are untouched
(TC-MIG-V3-00..06, `tests/unit/test_migration_v3.py`; source v2/v1
references preserved per fixture). KNOWN_ISSUES K-7 resolved. Sprint 3/4
saved-flow tests were redefined by the approved E5 scope. Full suite at
E5 completion: **414 passed, 0 failed**.

### Assignment §16 coverage map (E6 reconciliation, recorded 2026-10-14)

Negative cases — each maps to named, passing tests:

| §16 negative case | Tests |
|---|---|
| Unsupported file | `tests/unit/test_upload_gates.py` (extension/MIME gates); upload-flow rejections in `tests/integration/test_upload_flow.py` |
| Empty file | `tests/unit/test_upload_gates.py` (empty-content gate) |
| Invalid invoice data | `tests/unit/test_review_validation.py` (TC-S3-U01..U20), `tests/integration/test_review_save_flow.py` TC-S3-I08 |
| Missing mandatory field | `tests/unit/test_validation.py` (R1 mandatory-field suite), TC-S3-I08 |
| Invalid GSTIN | `tests/unit/test_validation.py` (W_GSTIN_FORMAT cases) |
| Incorrect total amount | `tests/unit/test_validation.py` (E_AMOUNT_PRIMARY_MISMATCH / W_DISCOUNT_EQUATION, inclusive-tolerance cases) |
| Malformed extraction response | `tests/unit/test_glm_response.py` (TC-RESP cases), `tests/integration/test_glm_extraction.py::test_malformed_response_reask_then_permanent` |
| Extraction failure | `tests/integration/test_async_pipeline.py` TC-PIPE-FAIL-01..06; scan gate TC-S4-I09 |
| Duplicate invoice | `tests/unit/test_duplicates.py`, `tests/integration/test_e3_validation.py` TC-E3-D01..03, save gate TC-S3-I14/I15 |
| Unauthorized approval | `tests/unit/test_approvals.py`, `tests/integration/test_e4_approval_flow.py` TC-ROLE/ACT (zero-write proofs) |
| Invalid status transition | `tests/unit/test_workflow.py` (illegal pairs, terminal states), TC-APPR-ACT-03, TC-S3-I12-class guards |

Integration flows — each maps to an executed flow test:

| §16 flow | Tests |
|---|---|
| Upload → Database | `test_upload_flow.py`, TC-S2-I01 (`test_extraction_flow.py`), TC-ASYNC-01 |
| Upload → Background Processing | `tests/integration/test_async_pipeline.py` (TC-ASYNC-01/02, recovery TC-RECV-*) |
| Extraction → Validation | `tests/integration/test_e3_validation.py` TC-E3-V01..V05 |
| Validation → Duplicate Check | TC-E3-V01 (dup none), TC-E3-D01..03 |
| Validation → Approval | `tests/integration/test_e4_approval_flow.py` TC-APPR-SUB/V04 (completed and validation_failed both submittable) |
| Approval → Audit History | TC-APPR-SUB-01 audit assertions, TC-APPR-ACT-02, TC-APPR-REJ-02; timeline UI TC-DETAIL-01 |

### E6 final-accuracy checklist (§19 documents + §20 structure)

To be executed and ticked only against verified content (US-E6-2):

- [ ] **README.md** — states what the app is, how to run it (venv, `run.py`), test command, and where docs live; no stale sprint counts.
- [ ] **docs/REQUIREMENTS.md** — functional/non-functional requirements, assumptions, dependencies, risks present (§19); check enhancement deltas referenced.
- [ ] **docs/USER_STORIES.md** — story IDs + acceptance criteria + priority + dependencies for every story (§19); §24 matrix rows match recorded evidence (reconciled 2026-10-14; AC-2/5/21 stay authorisation-gated).
- [ ] **docs/SPRINT_PLAN.md** — every sprint has goal, stories, tasks/outcome; E0–E5 statuses match acceptance records; E6 row updated when closed.
- [ ] **docs/ARCHITECTURE.md** — existing vs proposed, components, data flow, background processing, AI integration (§19); state model reflects v3 (no `extracted`/`saved`); §6 route map matches implemented routes.
- [ ] **docs/TEST_PLAN.md** — strategy, scenarios, negative cases, coverage (§19); every recorded number matches an executed run; §16 map present (this revision).
- [ ] **docs/KNOWN_ISSUES.md** — every entry has status + mitigation; K-1..K-5 open-by-design with mitigations; K-6/K-7 resolved; K-9 incident retained with live-migration authorisation note.
- [ ] **CLAUDE_USAGE.md** — §21 sections complete (exploration, planning, implementation, ≥2 debugging cases, ≥1 refactoring, code review); every entry traceable to recorded work; no fabricated events.
- [ ] **Repository structure (§20)** — README.md, docs/ six named files, CLAUDE_USAGE.md all present at the documented paths (verified present this revision); additional docs (01–16) allowed as "useful additions".
- [ ] **Numbers audit** — no document claims a test count or run that is not recorded in TEST_PLAN.md; the phrase "live smoke pending" only where true.

Sprint E4 is now executed: submission routing at the ₹1,00,000 boundary
and refusal rules (TC-APPR-SUB-01..04, `tests/unit/test_approvals.py`),
approve/reject with mandatory reasons and terminal-transition protection
(TC-APPR-ACT-01..03, TC-APPR-REJ-01/02), the role access matrix with
zero-write proofs for every wrong-role attempt (TC-ROLE-* in
`tests/integration/test_e4_approval_flow.py` — refusals assert the status,
decision columns, AND audit row count directly, never the HTTP code
alone), queue role-filtering, session role switching
(`tests/unit/test_roles.py`), and a full §12 lifecycle walk. No schema
changes; no new dependencies. Full suite at E4 completion: **397 passed,
0 failed** (independently re-confirmed at the acceptance review).
**Sprint E4 accepted 2026-10-14** (read-only acceptance review; see
SPRINT_PLAN.md). Outstanding, tracked outside E4 criteria: live GLM smoke
(E2 item, pending user key) and browser-level UI verification (E6).

Sprint E1 results are in §2b; Sprint E2 results in the run table above
(R-E2-1/2) and the E2 catalogue now executed: TC-GLM-*, TC-RESP-01..12,
TC-UPG-*, TC-KEY-01, TC-RAW-01 (truncation; UI-rendering half moves to E5),
fallback and unconfigured-AI behavior — see `tests/unit/test_glm_client.py`,
`tests/unit/test_glm_response.py`, `tests/integration/test_glm_extraction.py`.

Sprint E3 is now executed (the planned TC-VAL-INT-01/TC-DUP-* ids landed as
the TC-E3-* family): 33 validation-engine unit tests
(`tests/unit/test_validation.py`), 20 duplicate-classification unit tests
(`tests/unit/test_duplicates.py`), and 11 pipeline/detail integration tests
(`tests/integration/test_e3_validation.py`, TC-E3-V/D/U-*). One semantic
correction was required by the assignment's own evaluation samples
(docs/07 samples 2–5 are correctly discounted invoices):
`subtotal − discount + tax = total` governs discounted invoices with
Warning severity (approved decisions 1+4); the plain `subtotal + tax =
total` Error check applies when no discount is present. Fixture updates for
the new rules: the GLM stub response now carries line items that sum to the
subtotal, and the Sprint 4 history fixtures use digit-bearing invoice
numbers (the parser never extracted digit-less tokens like `INV-A`, which
§8.1 enforcement now surfaces). Full suite at E3 completion: 344 passed.

US-E3-3 direct evidence was added afterwards (TC-E3-XF-*): extraction
mapping (`test_glm_response.py`), prefill and invalid-value handling
(`test_review_validation.py`), and pipeline persistence, review-page
prefill and save/reload round-trip
(`tests/integration/test_e3_extended_fields.py`). Two of these tests
(TC-E3-XF-06, TC-E3-XF-I05) initially exposed a strict-validation defect —
`review._validate_lines` silently dropped a non-numeric `tax_{i}` to NULL
instead of blocking with a named error (the AC-04.2 decimal-field rule).
**Resolved 2026-10-13 (user-approved fix):** `_validate_lines` now rejects
a non-empty non-numeric per-line tax with `tax_{i}` named, consistent with
quantity/unit price/amount; both tests green. Full suite at E3 close:
**357 passed, 0 failed.**
