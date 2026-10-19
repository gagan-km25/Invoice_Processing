# E6 DEMONSTRATION SCRIPT (DRAFT) — assignment §23

Status: **functional rehearsal recorded 2026-10-18 (offline, isolated); browser-level walkthrough pending.** Every step marked **[RECORD]** carries its actual result below (see the demonstration-run record); nothing in this file claims a result that has not happened.

Preconditions (each requires the stated authorisation):
- App launch approved (browser-level verification + functional demo).
- Live GLM smoke approved (`ZAI_API_KEY` configured; model names
  confirmed per KNOWN_ISSUES K-5) — needed for the AI extraction step.
- Live database decision recorded: the next boot upgrades it v2 → v3
  (take/verify a timestamped backup first — K-9 precedent).
- E2–E5 commits merged or staged per the commit-authorisation decision.

---

## Part 1 — Functional demonstration (assignment §23, items 1–8)

Environment: local venv, `WORKER_AUTOSTART` per run.py, browser on
127.0.0.1, session role = vendor unless stated.

1. **Upload** **[RECORD]** — upload a text-layer PDF and a JPG/PNG image
   (with the GLM key configured, the image exercises the vision path);
   show the immediate response (processing continues in the background)
   and the record appearing on the upload page.
2. **Processing status** **[RECORD]** — open the detail page while
   processing: status badge `processing`, auto-refresh note; then the
   terminal status (`completed`, or `validation_failed` if the demo file
   is deliberately broken).
3. **Extraction** **[RECORD]** — the detail page shows the extracted
   header (all §6 fields: PO number, bill-to/ship-to, GSTIN, per-line
   tax), line items, and (if retained) the collapsed raw response.
4. **Validation** **[RECORD]** — the Validation panel with verdict and
   findings; use one file with a broken total to show a finding and the
   `validation_failed` status, then reprocess it corrected.
5. **Duplicate detection** **[RECORD]** — upload the same invoice twice;
   the second record shows the Duplicate check panel with the exact
   classification and the matched record named; processing is not
   blocked.
6. **Approval (submit → route)** **[RECORD]** — as vendor, submit a
   completed invoice; show the flash naming the routed role (demonstrate
   the ₹1,00,000 boundary with a second, larger invoice routed to
   finance).
7. **Approve / Reject** **[RECORD]** — switch the session role to the
   routed approver: the queue shows only matching records; approve one;
   reject the other with a typed reason; show the stored reason and
   `acted_by/at` on the rejected detail page; attempt a second decision
   on the approved record and show the refusal.
8. **Audit history** **[RECORD]** — the Audit history panel lists every
   event in order (uploaded, started, extraction, validation, submit,
   routed, approved/rejected, …) with actor and timestamp.

Also demonstrate: deletion blocked while `uploaded`/`processing`, allowed
elsewhere with confirmation; the all-status list with the status filter,
search, ID and Created columns; review & save prefill/correction.

## Part 2 — Technical walkthrough (assignment §23 topics)

Speaking order (each backed by a doc/code anchor):

1. **Architecture** — Flask app factory, thin routes, services layer,
   all SQL in the repository; docs/ARCHITECTURE.md.
2. **Database design** — schema v3 (invoices/lines/audit), the four
   status-adjacent dimensions as data columns, versioned migrations
   v1→v2→v3 with copy-rehearsal discipline; docs/ARCHITECTURE §5.
3. **Background processing** — single serial worker, job kinds and
   ownership, claim ladder, bounded per-episode retries, boot recovery;
   docs/ARCHITECTURE §4.
4. **AI integration** — GLM text/vision selection, strict response
   validation with one re-ask, size-capped raw retention, no silent
   fallback; docs/ARCHITECTURE §7.
5. **Error handling** — typed extraction failures, sanitised
   PipelineError, two-logger discipline with allowlist, generic 500;
   docs/ARCHITECTURE §8.
6. **Testing approach** — 414 offline tests (unit/integration),
   zero-write refusal proofs, migration rehearsals on copies; docs/
   TEST_PLAN.md + the §16 coverage map.
7. **Key design decisions** — discount-aware validation (docs/15),
   `saved` removal and the review/save rewire, session-roles-not-
   authentication, duplicates informational-only, workflow as the single
   transition authority.

## Part 3 — Claude Code demonstration (assignment §23)

Walk CLAUDE_USAGE.md top-to-bottom with the transcript as evidence:

- **Exploration** — read-only Phase-A exploration; docs/02 and docs/07
  produced before implementation.
- **Planning** — sprint plan, user stories, per-sprint decision records;
  the E3 correction rounds as the example of plan hardening.
- **Implementation** — E0–E5 entries; highlight test-driven development
  where the suite caught real defects during the build.
- **Debugging** — pick two live: D-10 (discount-equation conflict,
  resolved by evidence + a user-approved decision record) and D-11
  (line-tax silent drop, found by acceptance-evidence tests, fixed only
  after reporting); mention D-12/D-13 as further cases.
- **Refactoring** — the E5 lifecycle rewire (`saved` removal) and the
  repository transaction consolidation.
- **Code review** — the per-sprint read-only acceptance reviews; findings
  fixed only after reporting (E3 line-tax; docs/15 wording), rejected
  suggestions with reasons (docs/15 §5).

Be prepared for a small live change request: the review-and-fix cycle
recorded for M1/M2 (E1) demonstrates the workflow.

---

## Demonstration-run record (2026-10-18, offline functional rehearsal)

Method: the application's real routes and worker were driven in-process
(`create_app` + test client + `worker.run_pending()`) against an isolated
temporary database with the real key absent (local parser; no external
calls, no live-database access — live DB sha256-verified unchanged).
Data: synthetic only (the printed-fictional `sample_invoices/
invoice_003_multiitem.pdf` plus generated minimal PDFs/PNG). The in-app
HTTP interactions below are executed checks; the browser presentation of
this script and Parts 2–3 remain the presenter's live walkthrough.

| Step | Actual result (2026-10-18) |
|---|---|
| 1 Upload [RECORD] | **Executed.** Text PDF: HTTP 302 — record visible on the redirected page immediately (processing continues in background). PNG without the key: typed permanent failure with the user-safe message "AI extraction is not configured — images ... require the GLM vision model" (graceful no-key path). Vision success with the key was demonstrated separately in the recorded 2026-10-18 live smokes. |
| 2 Processing status [RECORD] | **Executed.** Record #3 showed `uploaded` before the worker ran and `completed` after; detail page HTTP 200; status endpoint `/invoices/<id>/status` HTTP 200. |
| 3 Extraction [RECORD] | **Executed.** Detail showed all §6 header fields (number MOS-88421, date, vendor, GSTIN, bill-to, currency INR, subtotal 14045.00, discount 750.00, tax 1595.40, total 14890.40) and 8 persisted line items. Raw-response panel correctly absent for a local-parser run (retention is GLM-only; shown in the recorded smoke). |
| 4 Validation [RECORD] | **Executed.** Broken-total file — `validation_failed` with finding `E_AMOUNT_PRIMARY_MISMATCH`; page showed the failed banner and findings list. Corrected file — `completed`. |
| 5 Duplicate detection [RECORD] | **Executed.** Same file re-uploaded — classification `exact` with both matched records named (ids + vendor + number + date + total); Duplicate panel rendered; processing NOT blocked (status `completed`). |
| 6 Approval routing [RECORD] | **Executed.** #1 (Rs 14,890.40) submitted — routed `manager` with the manager flash. #6 review & save raised the total to 150000.00 (duplicate-flagged save required explicit `confirm_duplicate` — the status-blind duplicate gate) and KEPT status `completed`; re-submit — routed `finance`. |
| 7 Approve / Reject [RECORD] | **Executed.** Manager queue showed only the manager-routed record; approve — `approved`, `acted_by=approver:manager`. Second decision on the approved record refused with flash "only pending_approval invoices can be approved or rejected", status stayed `approved`. Finance queue showed only the finance-routed record; reject with typed reason — `rejected`, `acted_by=approver:finance`, `acted_at` set, reason stored and displayed. A finance attempt on the manager-routed record was refused 403 (zero-write). |
| 8 Audit history [RECORD] | **Executed.** #6 audit events in order: uploaded, processing_started, extraction_completed, duplicate_detected, processing_completed, review_submitted, approval_assigned, invoice_rejected — panel with actors rendered. |
| Extras [RECORD] | **Executed.** Reprocess as approver — 403 (vendor-only). Delete of a completed record without confirm — confirmation page. Delete while `uploaded` — blocked with the cannot-be-deleted flash. History status filter + search + upload-date sort composed (approved filter + `q=MOS` + `sort=created` — HTTP 200, only matching rows). |
| Part 1 browser presentation | **Unexecuted here** — requires the approved app launch and a browser; the recorded checks above cover the same behaviour server-side. |
| Part 2 / Part 3 walkthroughs | **Unexecuted** — speaking material for the presenter; doc/code anchors verified to exist (ARCHITECTURE §1–§9, CLAUDE_USAGE, docs/02, docs/07, docs/15). |

Note: the earlier text in this file said "414 offline tests" (Part 2, item
6); the current recorded figures are 478 (2026-10-15) and 482 (verified
2026-10-18) — see TEST_PLAN.
