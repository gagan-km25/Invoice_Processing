# USER STORIES — Invoice Processing System Enhancement

Story IDs `US-E<sprint>-<n>`; priorities Must/Should. Each story lists its
acceptance criteria; "verified by" names the tests or manual checks that
must exist before the story is marked Done (recorded in TEST_PLAN.md).
Legacy baseline stories (US-1–US-12, US-S3/S4/S5) remain in the preserved
numbered docs and are not repeated here.

## Sprint E0 — baseline, schema v2, workflow/audit foundations

**US-E0-1 — Feature branch (Done).**
As a developer I create `enhancement/assignment` from `master@f69a193`
without disturbing the working tree, so prior work is preserved.
ACs: (1) branch exists; (2) `docs/05-prompt-log.md` (modified) and
`docs/14-execution-commands.md` (untracked) remain exactly as before; (3) no
reset/clean/stash used. *Verified by:* git status records before/after
(recorded in TEST_PLAN.md).

**US-E0-2 — Versioned schema migration v2 (Done).**
As the system I upgrade v1 databases in place — preserving IDs, field
values, timestamps, and line items — so existing records survive the
enhancement.
ACs: TC-MIG-01..07, TC-MIG-09 pass; copied-database rehearsal on the real
`data/invoices.db` passes and is recorded; the live DB itself is not
migrated in Sprint E0. *Verified by:* `tests/unit/test_migration.py` (9
tests) + rehearsal record.

**US-E0-3 — Configuration & environment safeguards (Done).**
As the system I read AI-provider settings from the environment so no key is
ever hard-coded or committed.
ACs: env overrides work; defaults contain no key material; `.env.example`
holds placeholders only; `.env` is git-ignored. *Verified by:*
`tests/unit/test_config.py`.

**US-E0-4 — Status machine + audit foundation (Done).**
As the system I enforce legal status transitions in one place and write an
audit entry with every status change, so the lifecycle is controlled (§12)
and history is maintained (§13).
ACs: every legal transition resolves; ≥15 illegal pairs raise
`InvalidTransition` (incl. Approved→Approved, Approved→Rejected); approval
boundary < ₹1,00,000 → manager / ≥ → finance; status+audit write atomically.
*Verified by:* `tests/unit/test_workflow.py` (31 tests).

**US-E0-5 — Documentation skeletons (Done).**
As a reviewer I find the exact Heading-20 documents with accurate content
and no fabricated results.
ACs: all six `docs/*.md` + root `CLAUDE_USAGE.md` exist; only recorded
results appear; future sections state "planned" rather than claiming
completion. *Verified by:* E6 TC-DOC-CHECK (sprint E0: manual inspection).

## Sprint E1 — asynchronous pipeline core (planned)

- **US-E1-1** Pipeline orchestrator + serial background worker (statuses
  `processing→completed/validation_failed/failed`). ACs: TC-PIPE-INT-*.
- **US-E1-2** Non-blocking upload + status endpoint + detail for all
  statuses. ACs: TC-ASYNC-01/02.
- **US-E1-3** Transient-failure retry (2× backoff) + reprocess action.
  ACs: TC-PIPE-FAIL-*.
- **US-E1-4** Audit events wired through the pipeline. ACs: TC-AUDIT-*.
- **US-E1-5** DEBUG off, structured logging, generic 500. ACs: TC-ERR-500-01.
- **US-E1-6** Restart recovery with job ownership: only recovery-designated
  jobs resume stale `processing` invoices; normal jobs skip; enqueue dedupe.
  ACs: TC-RECV-01..04.

## Sprint E2 — GLM extraction + images (planned)

- **US-E2-1** `glm_client.py` text + vision paths (stubbed in tests).
  ACs: TC-GLM-*.
- **US-E2-2** Response validator + draft conversion + raw retention.
  ACs: TC-RESP-01..12.
- **US-E2-3** JPG/PNG upload gates + correct serving mimetype + unconfigured
  AI failure messages. ACs: TC-UPG-*.
- **US-E2-4** Live smoke vs Z.ai (manual, recorded). ACs: recorded evidence.

## Sprint E3 — validation + duplicates + extended fields (planned)

- **US-E3-1** Business validation service (§8.1–8.5) with persisted verdicts.
  ACs: ≥20 unit tests + TC-VAL-INT-01.
- **US-E3-2** Duplicate classification with explanations. ACs: TC-DUP-*.
- **US-E3-3** PO number, bill-to/ship-to, per-line tax end-to-end.
  ACs: prefill + persistence tests.

## Sprint E4 — approval workflow (planned)

- **US-E4-1** Routing rule wired at submit; `approval_assigned` event.
  ACs: TC-APPR-ROUTE-*.
- **US-E4-2** Session roles + route map (role limits documented, not
  authentication). ACs: TC-ROLE-01..14.
- **US-E4-3** Approvals queue; approve/reject with mandatory reason; guards.
  ACs: TC-APPR-ACT-*/TC-APPR-REJ-*.

## Sprint E5 — views & lifecycle polish (planned)

- **US-E5-1** All-status list with status filter (+ Invoice ID column).
  ACs: TC-LIST-*.
- **US-E5-2** Detail panels: validation findings, duplicates, approval, audit
  timeline, raw response (collapsible). ACs: TC-DETAIL-*.
- **US-E5-3** Delete policy per lifecycle (blocked while `processing`).
  ACs: delete-guard tests. Includes the schema tightening migration
  (v3: drop deprecated `extracted`/`saved` CHECK values) once review/save is
  rewired.

## Sprint E6 — verification, docs, demo (planned)

- **US-E6-1** Full regression + real-DB-copy migration rehearsal record.
- **US-E6-2** TEST_PLAN results + KNOWN_ISSUES finalisation.
- **US-E6-3** CLAUDE_USAGE.md completed with genuine evidence only.
- **US-E6-4** End-to-end demo script + recorded dry run.
- **US-E6-5** Traceability matrix finalised (all 21 ACs evidenced).
