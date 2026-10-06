# 10 — Sprint 5 Design: Hardening, Edge Cases & OCR Gate

Phase: Sprint 5 planning (Sprints 0–4 complete at commit `6ac1de8`; suite
164/0/0). Date: 2026-10-06.
Status: **DRAFT — awaiting user approval before implementation.**
Sprint type: **hardening & verification** — no new features, no parser-behavior
changes beyond the one approved gap fix (§4, US-S5-01).

---

## 1. Sprint Objective

Harden what exists and prove it: audit edge cases and error paths against the
requirements, close the identified gaps with minimal, justified changes,
formally evaluate and decide the OCR gate, and run a full regression plus a
recorded manual acceptance pass over the five real invoices.

## 2. Current-State Assessment

- **Pipeline:** upload → validate → extract → review/edit → validate → save →
  history → search → details → view original → delete. All live and tested.
- **Suite:** 164 passed / 0 failed / 0 skipped (unit + integration).
- **Layering:** routes → services (uploading, extraction, review, invoices) →
  parser (pure) / repository. Parser untouched since Sprint 2.
- **Error-handling paths today:** upload gates (size → presence → extension →
  magic → open/encrypt → page cap) each flash a specific message and store
  nothing; extraction failures mark the record `failed` with a reason; save
  rolls back atomically; duplicates warn-and-require-confirmation; delete is
  POST-only with confirmation; Origin check 403s cross-site POSTs.
- **Known gap (found in this planning pass):** a **PDF with no text layer**
  (scan/image-only) is not explicitly detected. It passes the gates, extracts
  zero text, and lands as `extracted` with an all-missing draft — honest, but
  AC-7.1 requires a *specific* message ("likely a scan") instead of twelve
  silent "not found" flags. → US-S5-01.

## 3. Exploration Findings

**Five real invoices (re-inspected this phase, read-only):**

| invoice | pages | extractable text | images | tables | words |
|---|---|---|---|---|---|
| invoice_001_retail | 1 | 560 chars | 0 | 3 | 83 |
| invoice_002_services | 1 | 609 chars | 0 | 3 | 82 |
| invoice_003_multiitem | 1 | 752 chars | 0 | 3 | 115 |
| invoice_004_alternate | 1 | 613 chars | 0 | 3 | 90 |
| invoice_005_complex | 1 | 695 chars | 0 | 3 | 99 |

All are text-based (no images, rich text layers, consistent table structure).
Combined with the Sprint 2 accuracy result (65/65 fields, 23/23 lines),
**pdfplumber is demonstrably sufficient**.

**Edge-case audit vs. existing coverage:**

| Case | Covered today? | Sprint 5 action |
|---|---|---|
| Corrupt / empty / malformed PDF | ✅ gates (TC-S1-U04/U09, I04) | regression only |
| Password-protected PDF | ✅ gate (TC-S1-U11) | regression only |
| Oversize / excessive pages | ✅ gates (TC-S1-U10/U12, I05/I06) | regression only |
| Invalid upload type | ✅ gates (TC-S1-U05/U07/U08) | regression only |
| **PDF with no text layer (scan)** | ⚠ partially — lands `extracted` all-missing, no specific message | **fix: US-S5-01** |
| Missing required extracted fields | ✅ review flags + validation (TC-S3-*) | regression |
| Malformed dates / numerics | ✅ review validation (TC-S3-U03/U06) | regression |
| Unusual line items (blank/partial/negative) | ✅ (TC-S3-U10–U12, parser U-tests) | regression |
| Database failure mid-save | ✅ rollback (TC-S3-I11) | regression |
| Duplicate handling | ✅ upload warn + save confirm (TC-S3-I14/15) | regression |
| Safe deletion / cascade / orphans | ✅ (TC-S4-U11, I13) | regression |
| Search / original-file regression | ✅ (TC-S4-I04–I07, I20) | regression |
| No raw exceptions on **known** paths | ✅ per-path tests | add explicit audit test (US-S5-02) |
| Unhandled-exception exposure | accepted risk: DEBUG=True on a localhost-only single-user tool shows the Werkzeug debugger for *unknown* bugs — documented coupling (exploration §12); all known paths handled | document, no change |
| Data leakage between invoices | implicitly covered (record-scoped fetches) | make explicit (US-S5-03) |
| Security regression (Origin/403/405, traversal) | ✅ (TC-S3-I18, TC-S4-I16/I17/I20) | re-run in regression |
| **OCR** | not implemented; gate never formally evaluated | **gate assessment §5** |

## 4. User Stories & Acceptance Criteria

**US-S5-01 — Specific failure for scanned / no-text PDFs** (Must)
*As a user, when I upload a PDF that contains no selectable text, I want a
clear "likely a scan" failure instead of a page of empty fields.*
Rationale: closes the AC-7.1 gap; honest state for a fundamentally unreadable
input; cheap to implement (one text-length check in the extraction service).
- **AC-01.1** Given a valid PDF whose pages yield no text, extraction marks
  the record `failed` with a message naming the problem and next step
  ("no selectable text — the PDF is likely a scan; OCR is not available in
  this version, use a text-based PDF").
- **AC-01.2** The message appears in the upload flash and on the failed
  record; the app does not crash.
- **AC-01.3** Text-bearing PDFs are unaffected (regression: five real
  invoices still extract 65/65).

**US-S5-02 — Known failure paths never crash or leak** (Must)
*As a user, I want every anticipated failure handled gracefully so the app
always stays usable.*
- **AC-02.1** An explicit error-path audit test drives each known failure
  input through HTTP and asserts a 200/30x/4xx response with user-facing
  messaging — never an unhandled 500.
- **AC-02.2** Unknown-internal-bug exposure remains the documented accepted
  risk (DEBUG=True, localhost-only) — recorded, not changed.

**US-S5-03 — Invoice data isolation made explicit** (Must)
*As a user, I want proof that one invoice's data can never surface on another
invoice's pages.*
- **AC-03.1** Test: with two invoices saved, record A's page contains none of
  record B's values (and vice versa) — review, detail, and history.
- **AC-03.2** Test: review-page drafts are record-scoped (draft A on B's
  review URL never appears).

**US-S5-04 — Manual acceptance pass on the five real invoices** (Must)
*As the project owner, I want recorded end-to-end evidence that the five real
invoices work through the entire product, not just through tests.*
- **AC-04.1** Scripted acceptance run: upload all five via HTTP → each reaches
  review prefilled → each saves → history lists all five (newest first) →
  search finds each by number and vendor → each detail page matches the
  exploration expected values → one delete cycle (confirm) on a sacrificial
  duplicate upload.
- **AC-04.2** Evidence recorded in docs/04 (per-invoice PASS lines).

**US-S5-05 — OCR gate decision recorded** (Must)
*As the project owner, I want the OCR decision made on evidence and recorded.*
- **AC-05.1** The gate assessment (§5) is recorded in docs/04 + docs/10 with
  the decision and its evidence; docs/02's risk R-3 and README updated to
  state the outcome (OCR deferred as not required by current scope).

**US-S5-06 — Full regression & security re-verification** (Must)
*As the project owner, I want the whole suite plus security checks green
after any hardening change.*
- **AC-06.1** Complete suite green (164 + new Sprint 5 tests, 0 failed).
- **AC-06.2** Security re-checks pass: Origin 403, GET-delete 405, 404s,
  injection-safe search, contained file serving.

## 5. OCR Gate Assessment (evidence-based)

| Gate question | Answer | Evidence |
|---|---|---|
| Are the current five invoices text-based? | **Yes, all five** | 560–752 chars extractable text each; **0 images**; stable table structures (re-inspected this phase) |
| Can pdfplumber extract the required information? | **Yes, proven** | 65/65 exact field checks + 23/23 line items (Sprints 2–4) |
| Does the current requirement set *require* OCR? | **No** | OCR is FR-17 / US-11 — **Could** tier, explicitly gated (T-I); the Must tier is text-layer PDFs |
| Is an OCR engine available? | **No** | Tesseract absent (verified Sprints 0/2); installation is a manual system step |
| Would OCR add complexity without current benefit? | **Yes** | System install + rasterization pipeline + OCR-grade parsing tolerance + new tests — for zero invoices that need it |
| **Decision for Sprint 5** | **NO-GO — defer OCR** | Record decision + evidence in docs/04 and README; keep the graceful path: no-text PDFs now fail with a specific message (US-S5-01), so a future OCR tier slots into the extractor interface without rework |

The extractor stays pluggable (approved architecture), so a future OCR tier
requires no rework of routes, storage, or parser.

## 6. Test strategy

| Category | What / why | IDs | Expected |
|---|---|---|---|
| Unit — no-text detection | blank-page valid PDF → extraction fails with the scan message; text PDF unaffected | TC-S5-U01, U02 | specific `failed` reason / unchanged extraction |
| Integration — no-text path | HTTP upload of blank PDF → failed status + scan message + review refused (non-extracted) | TC-S5-I01, I02 | user-facing message, no crash |
| Integration — error-path audit | every known bad input replayed over HTTP (corrupt, empty, encrypted-fake, oversize, page-limit, wrong type, injection search, 404s, GET-delete) | TC-S5-I03 | no 500s, each with user-facing messaging |
| Integration — isolation | two invoices; assert no cross-appearance of values on review/detail/history | TC-S5-I04, I05 | zero leakage |
| Regression | complete existing suite | TC-S5-R01 | 164 + new, all green |
| Security re-checks | Origin 403 / GET-delete 405 / 404 / injection / contained serving | TC-S5-R02 | all pass |
| Real-invoice acceptance | five-invoice HTTP lifecycle incl. history/search/detail/delete cycle | TC-S5-M01–M06 | all PASS, evidence recorded |
| Manual | reviewer walkthrough of review page usability on a real invoice | TC-S5-M06 | recorded in docs/04 |

(~8 automated new tests + 6-step manual acceptance checklist.)

## 7. Risk analysis

| # | Risk | Mitigation |
|---|---|---|
| R-S5-1 | No-text threshold misfires on sparse-but-valid PDFs | High threshold only for *totally* empty text (< 20 chars across all pages); real samples are 560+ chars; regression re-run |
| R-S5-2 | Hardening changes regress Sprint 0–4 | Full-suite gate + five-invoice verification after every change; changes limited to the extraction service |
| R-S5-3 | Manual acceptance is irreproducible | Scripted HTTP steps with per-invoice PASS evidence recorded in docs/04 |
| R-S4-… disk space | C: drive was full earlier this project | Check free space before suite runs; clean pytest temp afterwards |
| R-S5-4 | OCR pressure later | Gate evidence + pluggable extractor keep a future OCR tier cheap and decision-reversible |

## 8. Scope boundaries

**In:** edge-case analysis, error-path audit, no-text-layer detection fix,
isolation tests, manual acceptance run, OCR gate decision + documentation,
security regression, test-coverage additions.
**Out:** UI redesign, auth, cloud, multi-user, analytics, AI, bulk operations,
export, email, new DB engine, edit-after-save, new invoice-management
features, **OCR implementation (gate = no-go)**, Sprint 6 finalization work
(final docs pass, retrospective, tagging).

## 9. Implementation plan (after approval)

1. `services/extraction.py`: add the no-text-layer check (≈5 lines + message) — the only production change.
2. `tests/`: TC-S5-U01/U02, TC-S5-I01–I05 (+ error-path audit) — new test file.
3. Run: new tests → full suite → five-invoice verification.
4. Manual acceptance run (server + HTTP steps) → record evidence.
5. Docs: docs/04 (results + OCR decision), docs/06, docs/02 (R-3 outcome note), README (status table + OCR note), CHANGELOG.

## 10. Definition of Done (Sprint 5)

No-text gap closed and tested · error-path audit green · isolation tests green ·
OCR decision recorded with evidence · full suite green (0 failed) · five real
invoices re-verified · manual acceptance evidence recorded · docs updated ·
single commit after approval.

## 11. Implementation amendments (recorded post-implementation)

1. **docs/02 left frozen** — the OCR outcome (NO-GO, deferred) is recorded in
   docs/04 and README instead of amending the frozen exploration doc; docs/02's
   R-3 note already framed OCR as optional.
2. **Duplicate banner dedupe** — the acceptance run surfaced the same record
   being listed twice in the duplicate banner (vendor+number and hash match);
   fixed in the save route under US-S5-02 (user-facing message quality).
3. **OneDrive incident** — the documented T-3/R-4 hazard materialized during
   the manual acceptance run (DB file re-synced mid-run); details and the
   user recommendation are in docs/04's issue log.
