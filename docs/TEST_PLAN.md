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

## 3. Planned catalogue (NOT yet run — listed for traceability, no results claimed)

- **E1:** TC-ASYNC-01/02, TC-PIPE-FAIL-*, TC-AUDIT-*, TC-ERR-500-01,
  TC-KEY-01, TC-LOG-01/02, TC-RAW-01/02, TC-RECV-01..04 (recovery job
  ownership incl. unexpected duplicate job).
- **E2:** TC-GLM-*, TC-RESP-01..12, TC-UPG-*, live smoke (manual, recorded).
- **E3:** validation unit suite (≥20), TC-VAL-INT-01, TC-DUP-*.
- **E4:** TC-APPR-ACT-*, TC-APPR-REJ-01/02, TC-ROLE-01..14.
- **E5:** TC-LIST-*, TC-DETAIL-*, delete guards, v3 schema-tightening tests.
- **E6:** full regression, TC-MIG-08 final rehearsal record, TC-DOC-CHECK,
  end-to-end demo dry run (manual, recorded).
