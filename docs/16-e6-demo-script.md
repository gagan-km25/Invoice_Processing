# E6 DEMONSTRATION SCRIPT (DRAFT) — assignment §23

Status: **draft** — every step marked **[RECORD]** is to be executed and
its actual result written here during the demonstration run. Nothing in
this file claims a result that has not happened.

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
