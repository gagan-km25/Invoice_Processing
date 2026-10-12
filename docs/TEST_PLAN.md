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

- **E2:** TC-GLM-*, TC-RESP-01..12, TC-UPG-*, TC-KEY-01, TC-RAW-01/02
  (raw-response retention arrives with the GLM client), live smoke (manual,
  recorded).
- **E3:** validation unit suite (≥20), TC-VAL-INT-01, TC-DUP-*.
- **E4:** TC-APPR-ACT-*, TC-APPR-REJ-01/02, TC-ROLE-01..14.
- **E5:** TC-LIST-*, TC-DETAIL-*, delete guards, v3 schema-tightening tests.
- **E6:** full regression, TC-MIG-08 final rehearsal record, TC-DOC-CHECK,
  end-to-end demo dry run (manual, recorded).

Sprint E1 results are in §2b. TC-AUDIT-* assertions are embedded in the
TC-ASYNC/TC-PIPE/TC-RECV event-sequence checks rather than separate tests.
