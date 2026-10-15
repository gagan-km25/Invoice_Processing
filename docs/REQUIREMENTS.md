# REQUIREMENTS — Invoice Processing System Enhancement

Source of truth: `Invoice_Processing_Enhancement_Assignment.txt` (25 headings,
21 acceptance criteria, read in full 2026-10-12; requirement inventory
reconciled 2026-10-14). Baseline: the completed "Invoice Extractor"
application (Sprints 0–6, commit `f69a193`).

Status markers: **Done** (built + verified with recorded offline test
evidence), **Done (offline)** (done offline; live verification still
pending), **Partial**, **Planned**, **Pending authorisation** (work that
exists but needs a user-approved live step). Nothing is marked Done without
a recorded test run or manual check.

## 0. Requirement inventory & traceability (assignment §1–25)

Every individual assignment requirement with a stable ID. Grouped only where
each sub-requirement stays explicitly named. "Story" = USER_STORIES.md ID;
"Evidence" = the recorded test/implementation artefact. AC-1..AC-21 (§24) map
through this table plus the §24 matrix in USER_STORIES.md.

| ID | § | Requirement | Story | Sprint | Evidence | Status |
|---|---|---|---|---|---|---|
| R-001 | §3.1 | Vendor can upload invoices | US-E2-1 | E2 | TC-UPG-*, TC-S2-I01 | Done |
| R-002 | §3.1 | Vendor can view submitted invoices (list) | US-E5-1 | E5 | TC-LIST-01..05 | Done |
| R-003 | §3.1 | Vendor can view processing status | US-E1-2 | E1 | TC-ASYNC-02 | Done |
| R-004 | §3.1 | Vendor can view extracted information | US-E2-1/US-E5-2 | E2/E5 | TC-DETAIL-* | Done |
| R-005 | §3.1 | Vendor can view validation errors/warnings | US-E3-1/US-E5-2 | E3/E5 | TC-E3-V*, TC-DETAIL-01 panel | Done |
| R-006 | §3.1 | Vendor can view duplicate warnings | US-E3-2/US-E5-2 | E3/E5 | TC-E3-D*, duplicate panel | Done |
| R-007 | §3.1 | Vendor can view the final status | US-E5-2 | E5 | status badge, all states | Done |
| R-008 | §3.2 | Approver can view invoices requiring approval | US-E4-2 | E4 | TC-ROLE queue filtering | Done |
| R-009 | §3.2 | Approver can review invoice details (view-only) | US-E4-2 | E4 | route-map matrix | Done |
| R-010 | §3.2 | Approver can review validation results | US-E4-2/US-E5-2 | E4/E5 | validation panel | Done |
| R-011 | §3.2 | Approver can approve an invoice | US-E4-3 | E4 | TC-APPR-ACT-02 | Done |
| R-012 | §3.2 | Approver can reject an invoice | US-E4-3 | E4 | TC-APPR-REJ-02 | Done |
| R-013 | §3.2 | Approver provides the rejection reason | US-E4-3 | E4 | TC-APPR-REJ-01/02 | Done |
| R-014 | §3 | Simple role mechanism (workflow, not auth) | US-E4-2 | E4 | TC-ROLE-*, ARCHITECTURE §6 | Done |
| R-015 | §4 | PDF/JPG/JPEG/PNG uploads supported | US-E2-3 | E2 | TC-UPG-* | Done (offline) |
| R-016 | §4 | Type/size/empty-file validation; centralised limit | US-E2-3 | E2 | test_upload_gates.py | Done |
| R-017 | §4 | Unique invoice ID + initial status | v1 baseline + US-E1-1 | v1/E0 | baseline suite | Done |
| R-018 | §4 | Upload does not block while extraction runs | US-E1-2 | E1 | TC-ASYNC-01 | Done |
| R-019 | §5 | Background processing with visible status | US-E1-2/US-E1-4 | E1 | TC-ASYNC-*, TC-RECV-* | Done |
| R-020 | §5 | Lifecycle statuses incl. `failed` | US-E1-1 | E0/E1 | TC-SM-* | Done |
| R-021 | §5 | Extraction failure → recorded, suitable state | US-E1-3 | E1 | TC-PIPE-FAIL-01..06 | Done |
| R-022 | §5 | Reprocess for failed invoices | US-E1-3 | E1 | TC-PIPE-FAIL-06 | Done |
| R-023 | §6 | §6 header fields extracted | US-E2-1/US-E3-3 | E2/E3 | TC-S2-*, TC-E3-XF-* | Done (offline) — currency validated against the offline ISO 4217 snapshot (164 active codes with minor-unit exponents incl. zero-decimal JPY/KRW); ambiguous symbols (¥) flagged, never guessed |
| R-024 | §6 | Line items incl. per-line tax | US-E2-1/US-E3-3 | E2/E3 | TC-E3-XF-I01/I04 | Done (offline) |
| R-025 | §6 | Scans/images processed via AI vision | US-E2-2 | E2 | TC-GLM-VISION/SCAN (offline) | Done (offline) |
| R-026 | §6 | Raw AI response retained for traceability | US-E2-1 | E2 | TC-RAW-01, TC-RAW-02 UI | Done (offline) |
| R-027 | §7 | Strict AI-response validation; safe failure | US-E2-2 | E2 | TC-RESP-* | Done |
| R-028 | §7 | One re-ask before terminal failure | US-E2-2 | E2 | malformed-response test | Done |
| R-029 | §8.1 | Mandatory fields (number/date/vendor/currency/total) | US-E3-1 | E3 | validation R1 suite | Done |
| R-030 | §8.2 | Amount equations with configurable tolerance | US-E3-1 | E3 | R2/R6 + line-sum tests; docs/15 | Done — amount parsing supports ₹/Rs./Rs/INR tokens and Indian digit grouping (1,25,000.00) as well as European decimal commas; split CGST/SGST/IGST component rows are summed and a combined tax row takes precedence (no double counting) |
| R-031 | §8.3 | Date rules (≤ today; due ≥ invoice) | US-E3-1 | E3 | R4 tests | Done |
| R-032 | §8.4 | GSTIN format check when present | US-E3-1 | E3 | R5 tests | Done |
| R-033 | §8.5 | Verdicts Passed/Warning/Failed + findings | US-E3-1 | E3 | TC-E3-V*, detail panel | Done |
| R-034 | §9 | Exact duplicate (vendor + number, case-insensitive) | US-E3-2 | E3 | test_duplicates.py | Done |
| R-035 | §9 | Possible duplicate (vendor + amount + date) | US-E3-2 | E3 | test_duplicates.py | Done |
| R-036 | §9 | Classification + explanation (no bare true/false) | US-E3-2 | E3 | TC-E3-D01..03, matches payload | Done |
| R-037 | §9 | Informational only + save-time gate (status-blind) | US-E3-2/US-E5-3 | E3/E5 | TC-E3-D01, TC-S3-I14 | Done |
| R-038 | §10 | Routing < ₹1,00,000 → manager; ≥ → finance | US-E4-1 | E4 | TC-APPR-ROUTE-01..04, SUB-01/02 | Done |
| R-039 | §10 | Routing implemented exactly once | US-E4-1 | E0/E4 | `workflow.required_approver` | Done |
| R-040 | §11 | Approve: pending → approved | US-E4-3 | E4 | TC-APPR-ACT-02 | Done |
| R-041 | §11 | Reject: pending → rejected | US-E4-3 | E4 | TC-APPR-REJ-02 | Done |
| R-042 | §11 | Rejection reason mandatory, stored, displayed | US-E4-3 | E4 | TC-APPR-REJ-01/02 | Done |
| R-043 | §11 | Invalid actions prevented (zero writes) | US-E4-3 | E4 | TC-APPR-ACT-03, TC-SM-03 | Done |
| R-044 | §12 | Documented lifecycle status set | US-E0-4 | E0 | `workflow.TRANSITIONS`, ARCHITECTURE | Done |
| R-045 | §12 | Single transition authority | US-E0-4 | E0 | `workflow.apply_transition` | Done |
| R-046 | §12 | Invalid transitions prevented | US-E0-4/US-E4-3 | E0/E4 | TC-SM-03, TC-APPR-ACT-03 | Done |
| R-047 | §13 | Audit event catalogue (§13 list) | US-E0-4 | E0 | audit.py `ALL_EVENTS` | Done |
| R-048 | §13 | What / which invoice / when / who per entry | US-E0-4 | E0/E4 | audit rows incl. actor | Done |
| R-049 | §13 | History accessible on the detail screen | US-E5-2 | E5 | TC-DETAIL-01 | Done |
| R-050 | §14 | List with ID/number/vendor/date/amount/status/created | US-E5-1 | E5 | TC-LIST-04 | Done |
| R-051 | §14 | Detail: info, extraction, lines, validation, duplicates, approval, audit | US-E5-2 | E3–E5 | TC-DETAIL-01..04 | Done (offline) |
| R-052 | §14 | Basic status filtering (+ search) | US-E5-1 | E5 | TC-LIST-01/03 | Done |
| R-053 | §15 | Meaningful errors; no tracebacks/sensitive data to users | US-E1-5 | E1 | TC-ERR-500-01 | Done |
| R-054 | §15 | Errors logged (structured, allowlisted) | US-E1-5 | E1 | TC-LOG-01/01b | Done |
| R-055 | §16 | Automated unit tests (validation/amounts/duplicates/approval/transitions) | all sprints | E0–E5 | 414-passing suite | Done |
| R-056 | §16 | Integration flows (6 listed chains) | E1/E3/E4/E5 | E1–E5 | §16 coverage map (TEST_PLAN) | Done |
| R-057 | §16 | Negative cases (11 listed areas) | all sprints | E1–E5 | §16 negative map (TEST_PLAN) | Done |
| R-058 | §17 | Clean code; separation; no overcomplexity | US-NFR-2/3 | continuous | architecture rules | Done |
| R-059 | §18/§21 | CLAUDE_USAGE.md with required sections | US-E6-3 | E6 | this revision | Done (E6 review pending) |
| R-060 | §19 | Requirements document | US-E0-5 | E0 | REQUIREMENTS.md | Done |
| R-061 | §19 | User-stories document | US-E0-5 | E0 | USER_STORIES.md | Done |
| R-062 | §19 | Sprint-plan document | US-E0-5 | E0 | SPRINT_PLAN.md | Done |
| R-063 | §19 | Architecture document | US-E0-5 | E0 | ARCHITECTURE.md | Done |
| R-064 | §19 | Testing document | US-E0-5 | E0 | TEST_PLAN.md | Done |
| R-065 | §20 | Minimum repository structure (README, docs/ six, CLAUDE_USAGE) | US-E0-5/US-E6-2 | E0/E6 | verified present 2026-10-14 | Done |
| R-066 | §22 | Meaningful messages; logical commits; branches | US-E0-1 | E0–E6 | E0/E1/E3–E5/E6 commits (`daeb9c2`, `b4bbee9`, `c5d6bee`, `795e5bf`, `c197e11`, `2e9b85a`) | Done — series recorded 2026-10-14 |
| R-067 | §22 | No secrets committed | US-NFR-4 | E0 | TC-KEY-01, `.env` git-ignored | Done |
| R-068 | §22 | Clear README | US-E6-2 | E6 | this rewrite | Done (review pending) |
| R-069 | §22 | Clean project history | US-E0-1 | E0–E6 | chronological per-sprint commits on `enhancement/assignment` | Done — recorded 2026-10-14 |
| R-070 | §23 | Functional demonstration (items 1–8) | US-E6-4 | E6 | docs/16 script | Pending authorisation |
| R-071 | §23 | Technical walkthrough | US-E6-4 | E6 | docs/16 Part 2 | Pending authorisation |
| R-072 | §23 | Claude Code usage demonstration | US-E6-4 | E6 | docs/16 Part 3 | Pending authorisation |
| R-073 | §24 | 21 acceptance criteria evidenced | US-E6-5 | E6 | §24 matrix (USER_STORIES) | Partial — live/demo rows open |
| R-074 | §25 | Process demonstration (understand→…→reflect) | US-E6-3/US-E6-4 | E6 | SDLC docs + CLAUDE_USAGE + reviews | Done (offline record); live walkthrough pending |

Coverage: 74 individual requirements; every assignment §3–§25 requirement is
represented. Not countable as requirements but recorded: §1/§2 context,
§13's event list is enumerated in `app/services/audit.py`, §24's 21 criteria
in the USER_STORIES §24 matrix.

## 1. Functional requirements (assignment §3–§14) — sprint status view

| ID | Requirement (assignment source) | Priority | Status |
|---|---|---|---|
| FR-E1 | Vendor/approver roles with the route map in ARCHITECTURE.md §6 (§3) | Must | **Done** (E4: TC-ROLE-*, route map implemented) |
| FR-E2 | Upload accepts PDF, JPG, PNG; validates type, size, empty files; size limit stays centralised (§4) | Must | **Done** (E2: gates + content signatures; TC-UPG-*) |
| FR-E3 | Upload returns before extraction completes (§4) | Must | **Done** (E1: TC-ASYNC-01) |
| FR-E4 | Unique invoice ID + appropriate initial status on upload (§4) | Must | **Done** (v1 baseline) |
| FR-E5 | Background processing with statuses Uploaded/Processing/Completed/Failed (+ Pending Approval, Validation Failed, Approved, Rejected per §12) (§5) | Must | **Done** (E1 worker + E4 approval statuses; TC-ASYNC-*, TC-SM-*) |
| FR-E6 | Graceful extraction-failure handling + retry for retryable failures (§5) | Must | **Done** (E1: TC-PIPE-FAIL-01..06) |
| FR-E7 | Extraction of all §6 fields: invoice number/date, due date, vendor, GSTIN, currency, PO number, subtotal, tax, total; bill-to/ship-to names + addresses; line items with description, quantity, unit price, tax, line total (§6) | Must | **Done** (E2 GLM + local fallback; extended fields E3; TC-E3-XF-*) |
| FR-E8 | Structured storage + retention of the raw AI response for traceability (§6) | Must | **Done** (E2: size-capped `raw_response`; TC-RAW-01) |
| FR-E9 | AI response validation before use: missing fields, invalid JSON, wrong types, invalid dates/numbers; malformed responses never crash and land in a failure state with a recorded error (§7) | Must | **Done** (E2: strict validator + one re-ask; TC-RESP-*, TC-GLM-UNAVAIL-*) |
| FR-E10 | Mandatory-field validation: invoice number, invoice date, vendor name, currency, total amount (§8.1) | Must | **Done** (E3: validation R1 suite) |
| FR-E11 | Amount validation: subtotal + tax = total; line-item sum = subtotal; configurable tolerance (default ₹0.01) (§8.2) | Must | **Done** (E3: R2/R3/R6; discount-aware rule per docs/15) |
| FR-E12 | Date validation: invoice date ≤ current date; due date ≥ invoice date (§8.3) | Must | **Done** (E3: R4) |
| FR-E13 | GSTIN format validation when present (§8.4) | Must | **Done** (E3: R5) |
| FR-E14 | Validation verdicts Passed/Warning/Failed with human-readable findings (§8.5) | Must | **Done** (E3: verdict + findings persisted; detail panel E5) |
| FR-E15 | Duplicate detection: exact (vendor + invoice number) and possible (vendor + amount + date), classified No/Possible/Exact with an explanation, never a bare true/false (§9) | Must | **Done** (E3; save gate rewired status-blind in E5) |
| FR-E16 | Approval routing: < ₹1,00,000 → manager; ≥ ₹1,00,000 → finance; implemented exactly once (§10) | Must | **Done** (E4: TC-APPR-ROUTE-*, SUB-01/02) |
| FR-E17 | Approve/reject actions; rejection reason mandatory; invalid transitions prevented (§11) | Must | **Done** (E4: TC-APPR-ACT/REJ-*) |
| FR-E18 | Controlled status lifecycle with documented transitions (§12) | Must | **Done** (machine E0 + pipeline E1 + approval transitions E4) |
| FR-E19 | Audit history of §13 events with what/which invoice/when/who; visible on the detail screen (§13) | Must | **Done** (E0 catalogue, E1 wiring, E5 timeline UI: TC-DETAIL-01) |
| FR-E20 | Invoice list (ID, number, vendor, date, amount, status, created) + detail (info, extraction, lines, validation, duplicates, approval, audit); status filter (§14) | Must | **Done** (E5: TC-LIST-*, TC-DETAIL-*) |
| FR-E21 | Meaningful error handling for the §15 catalogue; no stack traces or sensitive data to users; errors logged (§15) | Must | **Done** (E1 pipeline/logging + E2/E3 feature-level guards; TC-ERR/LOG) |

## 2. Non-functional requirements

| ID | Requirement | Status |
|---|---|---|
| NFR-E1 | Localhost-only binding preserved (baseline NFR-1) | **Done** (unchanged) |
| NFR-E2 | Separation of concerns: thin routes → services → repository-only SQL (§17) | **Done** (E0; restored for duplicates in E3) |
| NFR-E3 | No unnecessary complexity: no broker, no ORM, no new front-end stack (§17) | **Done** (E0) / continuous |
| NFR-E4 | Secrets: API key via environment only; never committed, logged, or returned to users (§17/§22) | **Done** (E0 plumbing + TC-CFG/TC-KEY tests) |
| NFR-E5 | Data privacy: invoice content leaves the machine only during GLM extraction, disclosed in README/KNOWN_ISSUES (§15) | **Done** (E2: implemented + disclosed; live smoke pending user key) |
| NFR-E6 | Logging: structured allowlist events; tracebacks only in the errors log of sanitised exceptions (§15) | **Done** (E1: applog allowlist enforced structurally; TC-LOG-01b, TC-ERR-500-01) |
| NFR-E7 | Migration safety: live DB never migrated before a recorded copy rehearsal; timestamped backup before any live migration. **Live-database situation (recorded decision):** the live database was retained at schema v2 by user decision (2026-10-12, Option B — see K-9). The next authorised application startup upgrades it v2 → v3 automatically; that step requires explicit authorisation and a fresh timestamped backup first. The live database has **not** been migrated to v3. | Recorded decision + rehearsal discipline intact (v3 copy rehearsal TC-MIG-V3-00/00b passed on disposable copies 2026-10-14) |
| NFR-E8 | Tests run against temporary databases only (baseline NFR-8) | **Done** (unchanged) |

## 3. Assumptions (recorded, per approved plan)

1. Approval threshold is applied to the numeric total regardless of currency.
2. Roles are session-based labels (no authentication) — the machine owner is
   the sole vendor; the mechanism demonstrates and enforces the role
   *workflow*, and is not a security boundary.
3. "Current date" for §8.3 means the local date at validation time.
4. The machine owner acts as the single vendor; per-vendor isolation is out
   of scope (no vendor identity exists in the assignment or the baseline).
5. GLM model names (`glm-4.6` text, `glm-4.5v` vision) are env-overridable
   defaults, to be confirmed against the real account at the Sprint E2 live
   smoke and recorded.

## 4. Dependencies

- Z.ai GLM API (key supplied by the user; endpoint and capabilities verified
  2026-10-12 — see ARCHITECTURE.md §7). Needed from E2 onward.
- `pypdfium2` + `pillow` (already installed transitively) for scanned-PDF
  rasterisation.
- One pinned HTTP client for the GLM call (decision 1: `requests`) — added
  in E2, not needed for E0.

## 5. Risks

| ID | Risk | Mitigation |
|---|---|---|
| R-1 | OneDrive sync vs SQLite writes (baseline risk T-3), now with a background writer | Serial worker, short transactions, busy_timeout at E1; documented pause-sync advice |
| R-2 | Vision model has no native JSON mode (verified) | Strict prompt + response validator + one re-ask; raw response stored for diagnosis |
| R-3 | Network/API unavailable at demo time | Decision 4: local-rules fallback for text PDFs; scans/images fail with a clear message |
| R-4 | API key leakage | Env-only, `.env` git-ignored, TC-KEY/TC-LOG tests, structural log allowlist |
| R-5 | Migration regressions on real data | Copy-based test suite + recorded copy rehearsals (v1→v2 passed 2026-10-12; v2→v3 passed 2026-10-14 with source-preservation proof) + timestamped backup before any live run |

## 6. Legacy baseline

The v1 application (upload → local-rules extraction → human review → save →
history) was fully functional during the early enhancement sprints; its own
SDLC documents are preserved unmodified under `docs/01-…`–`docs/13-…`. The
two v1 statuses `extracted`/`saved` existed only as transitional schema
values: review/save was rewired in Sprint E5 (save keeps a record at
`completed`) and the v3 migration removed both values from the schema CHECK.
The **live database** is still at schema v2 (retained by recorded decision,
see NFR-E7) and upgrades to v3 only at the next authorised startup.
