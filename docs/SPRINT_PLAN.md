# SPRINT PLAN — Invoice Processing System Enhancement

Approved plan of record (user-approved 2026-10-12, including the six
decisions, recovery-job ownership, and logging amendments). Baseline:
`master@f69a193` on branch `enhancement/assignment`. Dependency order is
strictly top-to-bottom.

| Sprint | Goal | Stories | Expected outcome (measurable) |
|---|---|---|---|
| **E0** | Baseline, schema v2 migration, workflow/audit foundations, canonical docs | US-E0-1..5 | Branch exists; migration preserves IDs/values/timestamps/lines (TC-MIG-01..07, 09); copy rehearsal PASS recorded; transition + threshold tests green; full suite green; docs skeletons accurate |
| **E1** | Asynchronous pipeline core on the existing local extractor | US-E1-1..6 | Upload returns before processing; status endpoint; retry + reprocess; audit events; logging + DEBUG off; restart recovery with job ownership |
| **E2** | GLM extraction (text + vision) + JPG/PNG | US-E2-1..4 | Structured §6 extraction incl. new fields; malformed responses handled (TC-RESP); image gates; live smoke recorded |
| **E3** | Business validation + duplicate classification + extended fields | US-E3-1..3 | §8 verdicts with findings; duplicates classified with explanations; review form covers all §6 fields |
| **E4** | Approval workflow + roles | US-E4-1..3 | ₹1,00,000 routing; queue; approve/reject with mandatory reason; role route map enforced |
| **E5** | Views & lifecycle polish | US-E5-1..3 | All-status list + filter; detail panels; delete guards; schema tightening (v3) |
| **E6** | Verification, docs, demo | US-E6-1..5 | Recorded regression; complete Heading-20 docs; genuine CLAUDE_USAGE.md; demo run; all 21 ACs evidenced |

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
