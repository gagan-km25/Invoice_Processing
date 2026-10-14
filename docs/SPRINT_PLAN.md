# SPRINT PLAN — Invoice Processing System Enhancement

Approved plan of record (user-approved 2026-10-12, including the six
decisions, recovery-job ownership, and logging amendments). Baseline:
`master@f69a193` on branch `enhancement/assignment`. Dependency order is
strictly top-to-bottom.

| Sprint | Goal | Stories | Expected outcome (measurable) |
|---|---|---|---|
| **E0** | Baseline, schema v2 migration, workflow/audit foundations, canonical docs | US-E0-1..5 | **Done** — commit `daeb9c2`; copy rehearsal PASS; 220 tests green |
| **E1** | Asynchronous pipeline core on the existing local extractor | US-E1-1..6 | **Done and committed at `b4bbee9`** — upload returns before processing (TC-ASYNC-01/02); bounded retries + reprocess (TC-PIPE-FAIL-*); recovery + job ownership + dedupe (TC-RECV-01..04); logging/500 hardening (TC-ERR-500-01, TC-LOG-01/01b); 240 tests green. Live-DB incident R-E1-8 **resolved** under TEST_PLAN.md R-E1-9 (user decision Option B: schema v2 retained; verified backup created) |
| **E2** | GLM extraction (text + vision) + JPG/PNG | US-E2-1..4 | **Done (implemented; live smoke pending user key)** — GLM text/vision extraction with strict response validation, one re-ask, raw retention, unconfigured fallback per decision 1, image gates + MIME serving; extended §6 fields (PO/ship-to/line tax) move to E3 with the schema work |
| **E3** | Business validation + duplicate classification + extended fields | US-E3-1..3 | **Done (implemented; uncommitted)** — §8 validation engine (severity per approved decisions 1+4; the discount-aware equation `subtotal − discount + tax = total` governs discounted invoices with Warning severity, the plain equation stays an Error; decision record docs/15); duplicates classified exact/possible/none with explanations, informational only; §6 extended fields (PO number, bill-to/ship-to, per-line tax) end-to-end — GLM schema, persistence, review form, detail panels; direct US-E3-3 evidence tests added (TC-E3-XF-*), including the strict-validation defect they exposed (non-numeric per-line tax now blocked with a named error, fixed 2026-10-13); **357 tests green** |
| **E4** | Approval workflow + roles | US-E4-1..3 | **Accepted 2026-10-14 (implemented; uncommitted)** — vendor submission routes by amount at the ₹1,00,000 boundary (`workflow.required_approver`, single authority); NULL totals refused with a clear message, never defaulted to Finance (approved decision 1); `saved` outside the flow (decision 3); session roles per ARCHITECTURE §6 (route-map revision recorded: `submit` + `/session/role` added) — wrong-role attempts 403 with zero database/audit writes (asserted directly); approve/reject matching-role-only, mandatory rejection reason stored + displayed; submit/approve/reject each write status + columns + audit in ONE transaction; invalid transitions refused by the §12 authority; **397 tests green, independently re-confirmed at the read-only acceptance review** (40 new: TC-APPR-SUB-01..04, TC-APPR-ACT-01..03, TC-APPR-REJ-01/02, TC-ROLE-*, queue filtering). Outstanding (tracked, not E4 criteria): live GLM smoke (E2 item, pending user key) and browser-level UI verification (E6) |
| **E5** | Views & lifecycle polish | US-E5-1..3 | **Done (implemented; uncommitted)** — all-status invoice list with exact-status filter, search, ID + Created columns (§14); detail audit-timeline panel and retained raw response rendered collapsed + HTML-escaped (TC-RAW-02 UI half); review/save rewired — save persists values and KEEPS the lifecycle status (no `saved` writes); duplicate gate now status-blind (any record, self-excluded — approved decision); deletion blocked while `uploaded`/`processing` (approved decision 1), confirm-guarded otherwise; **schema v3** tightening migration (transitional CHECK values dropped, remapped rows → `completed` with `legacy_status` + `record_migrated` audit, fk-gate, `user_version = 3`) — copy-rehearsal evidence recorded (TC-MIG-V3-00/00b: source bytes identical); KNOWN_ISSUES K-7 resolved; suite green (see TEST_PLAN) |
| **E6** | Verification, docs, demo | US-E6-1..5 | Recorded regression; complete §20-required documentation; genuine CLAUDE_USAGE.md; demo run; all 21 ACs evidenced |

## Sprint E0 task breakdown (this sprint)

| Task | Story | Result |
|---|---|---|
| Working-tree inspection + branch creation | US-E0-1 | Done (git records in TEST_PLAN.md) |
| `Config`: env-derived GLM settings, threshold, tolerance, status list | US-E0-3 | Done |
| `schema.sql` v2 (8-state lifecycle + transitional CHECK, audit table, indexes) | US-E0-2 | Done |
| `migrations.py` v1→v2 (table rebuild, status mapping, audit rows, FK gate) | US-E0-2 | Done |
| Versioned `init_db` (fresh / v1 / v2 paths, refuse-unknown guard) | US-E0-2 | Done |
| `workflow.py` transition machine + approval rule; `audit.py` catalogue; repository `insert_audit`/`get_audit`/`transition_status` | US-E0-4 | Done |
| Migration + workflow + config test files; conftest `make_app_config` | US-E0-2/3/4 | Done |
| Copied-database rehearsal vs live `data/invoices.db` (read-only source) | US-E0-2 | Done — PASS (recorded in TEST_PLAN.md) |
| Six canonical docs + CLAUDE_USAGE.md skeletons with accurate content | US-E0-5 | Done |
| Full regression run | gate | Done — 220 passed (169 legacy + 51 new) |

## Sprint E1–E5 task records (as implemented; evidence in TEST_PLAN.md)

Task breakdowns for E1–E5 are recorded here from the implemented work and
recorded test runs — no invented tasks. Each bullet cites its tests.

- **E1 (US-E1-1..6).** Async pipeline core (`app/services/pipeline.py`:
  serial worker, job kinds/ownership, enqueue dedupe, claim ladder,
  bounded retries, sanitised containment); extraction reworked to the
  pluggable core; structured `applog`; status endpoint; reprocess route;
  DEBUG=False + generic 500; boot recovery. Tests: TC-ASYNC-01/02,
  TC-PIPE-FAIL-01..07, TC-RECV-01..04, TC-DBLOCK-01..04, TC-ERR-500-01,
  TC-LOG-01/01b. Review fixes M1 (per-episode retries) and M2 (lock
  retry/resume). 240 passed at close.
- **E2 (US-E2-1..4).** GLM client (text JSON-mode + vision), extraction
  flow with strict validation/one re-ask/raw retention, upload gates for
  JPG/JPEG/PNG with content signatures, rasterization (≤3 pages),
  unconfigured-AI behaviour. Tests: TC-GLM-*, TC-RESP-*, TC-UPG-*,
  TC-KEY-01, TC-RAW-01. Review fixes M-A/M-B/L-A/L-B/L-C (incl. H-1
  vision-model mis-call). 280 passed at close. Live smoke: still pending.
- **E3 (US-E3-1..3).** §8 validation engine, duplicate classifier,
  pipeline validation/duplicate wiring (T2/T3), §6 extended fields
  end-to-end (GLM schema + coercion, persistence, review form, detail
  panels), acceptance-evidence suite TC-E3-XF-*, decision record docs/15
  (discount-aware equations), line-tax strict-validation fix (D-11).
  357 passed at close.
- **E4 (US-E4-1..3).** Submission routing (one transaction: status +
  `approver_role` + `review_submitted` + `approval_assigned`),
  approve/reject with mandatory stored reasons, session-role mechanism +
  route-map guards (zero-write refusals), role-filtered queue,
  terminal-transition protection. Tests: TC-APPR-SUB-01..04,
  TC-APPR-ACT-01..03, TC-APPR-REJ-01/02, TC-ROLE-*. 397 passed at close.
- **E5 (US-E5-1..3).** All-status list + status filter + ID/Created
  columns; audit-timeline and escaped collapsed raw-response panels;
  save-flow rewire (`saved` removed; duplicate gate status-blind);
  deletion guards for `uploaded`/`processing`; schema v3 tightening
  migration with copy-rehearsal source-preservation tests. Tests:
  TC-LIST-01..05, TC-DETAIL-01..04, TC-MIG-V3-00..06, redefined TC-S3/S4
  saved-flow cases. 414 passed at close.

Requirement → sprint traceability: see docs/REQUIREMENTS.md §0
(R-001…R-074, every assignment requirement mapped to a story, sprint, and
evidence artefact).

## Definition of Done (per sprint)

Full suite green (real run, counts recorded) · new ACs verified by named
tests or recorded manual checks · `git status` clean of unintended changes ·
protected files (`docs/05-prompt-log.md`, `docs/14-execution-commands.md`)
still present and unstaged · one meaningful commit on
`enhancement/assignment` with explicit-path staging.

## Sprint gate discipline

No sprint starts before the previous one's gate passes. Test counts are
recorded honestly in TEST_PLAN.md; failures are recorded as failures, then
fixed and re-run.
