# REQUIREMENTS — Invoice Processing System Enhancement

Source of truth: `Invoice_Processing_Enhancement_Assignment.txt` (25 headings,
21 acceptance criteria, read in full 2026-10-12). Baseline: the completed
"Invoice Extractor" application (Sprints 0–6, commit `f69a193`).
Status markers: **Planned** (sprint assigned, not yet built), **Done**
(built + verified with recorded evidence). Nothing is marked Done without a
recorded test run or manual check.

## 1. Functional requirements (assignment §3–§14)

| ID | Requirement (assignment source) | Priority | Status |
|---|---|---|---|
| FR-E1 | Vendor/approver roles with the route map in ARCHITECTURE.md §6 (§3) | Must | Planned (E4) |
| FR-E2 | Upload accepts PDF, JPG, PNG; validates type, size, empty files; size limit stays centralised (§4) | Must | Planned (E2) |
| FR-E3 | Upload returns before extraction completes (§4) | Must | **Done** (E1: TC-ASYNC-01) |
| FR-E4 | Unique invoice ID + appropriate initial status on upload (§4) | Must | **Done** (v1 baseline) |
| FR-E5 | Background processing with statuses Uploaded/Processing/Completed/Failed (+ Pending Approval, Validation Failed, Approved, Rejected per §12) (§5) | Must | **Done** (E1: serial in-process worker; approval statuses arrive E4) |
| FR-E6 | Graceful extraction-failure handling + retry for retryable failures (§5) | Must | **Done** (E1: TC-PIPE-FAIL-01..06) |
| FR-E7 | Extraction of all §6 fields: invoice number/date, due date, vendor, GSTIN, currency, PO number, subtotal, tax, total; bill-to/ship-to names + addresses; line items with description, quantity, unit price, tax, line total (§6) | Must | Planned (E2/E3) |
| FR-E8 | Structured storage + retention of the raw AI response for traceability (§6) | Must | Planned (E2) |
| FR-E9 | AI response validation before use: missing fields, invalid JSON, wrong types, invalid dates/numbers; malformed responses never crash and land in a failure state with a recorded error (§7) | Must | Planned (E2) |
| FR-E10 | Mandatory-field validation: invoice number, invoice date, vendor name, currency, total amount (§8.1) | Must | Planned (E3) |
| FR-E11 | Amount validation: subtotal + tax = total; line-item sum = subtotal; configurable tolerance (default ₹0.01) (§8.2) | Must | Planned (E3) |
| FR-E12 | Date validation: invoice date ≤ current date; due date ≥ invoice date (§8.3) | Must | Planned (E3) |
| FR-E13 | GSTIN format validation when present (§8.4) | Must | Planned (E3) |
| FR-E14 | Validation verdicts Passed/Warning/Failed with human-readable findings (§8.5) | Must | Planned (E3) |
| FR-E15 | Duplicate detection: exact (vendor + invoice number) and possible (vendor + amount + date), classified No/Possible/Exact with an explanation, never a bare true/false (§9) | Must | Planned (E3) |
| FR-E16 | Approval routing: < ₹1,00,000 → manager; ≥ ₹1,00,000 → finance; implemented exactly once (§10) | Must | Planned (E4) |
| FR-E17 | Approve/reject actions; rejection reason mandatory; invalid transitions prevented (§11) | Must | Planned (E4) |
| FR-E18 | Controlled status lifecycle with documented transitions (§12) | Must | **Done** (machine E0 + pipeline wiring E1); approval transitions arrive E4, review submit E3/E5 |
| FR-E19 | Audit history of §13 events with what/which invoice/when/who; visible on the detail screen (§13) | Must | **Done** (table+service E0; lifecycle events wired E1); **timeline UI Planned** (E5) |
| FR-E20 | Invoice list (ID, number, vendor, date, amount, status, created) + detail (info, extraction, lines, validation, duplicates, approval, audit); status filter (§14) | Must | Planned (E5) — detail available for all statuses since E1 |
| FR-E21 | Meaningful error handling for the §15 catalogue; no stack traces or sensitive data to users; errors logged (§15) | Must | Partial — **Done for pipeline/logging (E1)**; remaining catalogue cases arrive with E2/E3 features |

## 2. Non-functional requirements

| ID | Requirement | Status |
|---|---|---|
| NFR-E1 | Localhost-only binding preserved (baseline NFR-1) | **Done** (unchanged) |
| NFR-E2 | Separation of concerns: thin routes → services → repository-only SQL (§17) | **Done** (E0 code follows it) |
| NFR-E3 | No unnecessary complexity: no broker, no ORM, no new front-end stack (§17) | **Done** (E0) / continuous |
| NFR-E4 | Secrets: API key via environment only; never committed, logged, or returned to users (§17/§22) | **Done** (E0 plumbing + TC-CFG/TC-KEY tests) |
| NFR-E5 | Data privacy: invoice content leaves the machine only during GLM extraction, disclosed in README/KNOWN_ISSUES (§15) | Planned (E2 disclosure) |
| NFR-E6 | Logging: structured allowlist events; tracebacks only in the errors log of sanitised exceptions (§15) | **Done** (E1: applog allowlist enforced structurally; TC-LOG-01b, TC-ERR-500-01) |
| NFR-E7 | Migration safety: live DB never migrated before a recorded copy rehearsal; timestamped backup before any live migration | **Breached 2026-10-12 (E1 incident R-E1-8): an in-process boot migrated the live DB without authorization; restoration drafted, awaiting user decision. Rehearsal itself had passed (R-E0-4)** |
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
| R-5 | Migration regressions on real data | Copy-based test suite + recorded copy rehearsal (passed 2026-10-12) + timestamped backup before any live run |

## 6. Legacy baseline

The v1 application (upload → local-rules extraction → human review → save →
history) remains fully functional during the enhancement; its own SDLC
documents are preserved unmodified under `docs/01-…`–`docs/13-…`. The two
v1 statuses `extracted`/`saved` exist only as transitional schema values
until Sprint E5 rewires review/save onto the new lifecycle.
