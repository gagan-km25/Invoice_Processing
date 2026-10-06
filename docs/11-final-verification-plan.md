# 11 — Sprint 6 Plan: Final Verification, Documentation & Evaluation Readiness

Phase: Sprint 6 planning (Sprints 0–5 complete at commit `d22b855`; suite
169/0/0). Date: 2026-10-06.
Status: **DRAFT — awaiting user approval before finalization work.**
Sprint type: **finalization and verification only** — no features, no parser
changes, no schema changes, no OCR, no UI redesign.

---

## 1. Sprint Objective

Make the completed project fully **verified, documented, explainable, and
evaluation-ready**: consolidate requirement traceability, run the final
verification pass, close the audit findings below, and produce the
retrospective and evaluation Q&A — with every claim backed by evidence that
already exists or is produced by a check in this sprint.

## 2. Current-State Assessment

Complete and verified: the full pipeline (upload → validate → extract →
review/edit → save → history → search → details → original → delete), six
commits (one per sprint), 169/0/0 tests, five real invoices verified at 65/65
repeatedly, OCR gate NO-GO recorded, security checks green, isolation proven.

**Audit findings (issues found — none silently fixed during planning):**

| # | Type | Finding | Sprint 6 action |
|---|---|---|---|
| A-1 | Stale info | README *Prerequisites* still says "Tesseract OCR — only needed from Sprint 5 onward; install steps will be added then" — stale since the Sprint 5 NO-GO | Update README (remove Tesseract prerequisite; state the gate decision) |
| A-2 | Stale info | README documentation table lists docs 01–09 but not docs/10 | Add docs/10 (+ docs/11–13 when created) |
| A-3 | Traceability | No consolidated requirement→story→AC→implementation→test→evidence matrix exists (the evidence is scattered across docs/01–04) | Build the matrix in docs/11 (see §3) |
| A-4 | Traceability GAP | **FR-14 (Should) is partially covered**: search ✅; **date-range filter ✗ and user-selected sort ✗** were not implemented (Sprint 4's approved stories covered search only) | Mark **GAP — deferred by Sprint 4 scope decision**; do not implement |
| A-5 | Traceability GAP | **FR-11 / US-8 (Should) edit-after-save**: deferred in Sprint 4 (documented docs/09 §8) | Mark **GAP — deferred by decision** |
| A-6 | Traceability GAP | **FR-18 / US-12 (Could) CSV export**: never implemented (plan made it "if selected"; never selected) | Mark **GAP — Could tier not selected** |
| A-7 | Traceability GAP | **FR-17 / US-11 OCR**: gate NO-GO, deferred with evidence | Mark **GAP — deferred by gate decision (docs/10 §5)** |
| A-8 | Evidence | NFR-9 portability ("fresh-Windows setup") was verified once in Sprint 0 but not re-verified against the final code | Re-verify: clean venv → install → boot → smoke, recorded in docs/04 |
| A-9 | Evidence | Final consolidated verification evidence (one place listing everything green) does not yet exist | Produce docs/11 final-verification record |
| A-10 | SDLC evidence | Retrospective does not exist yet (SDLC goal item) | Create docs/12 (plan §7) |
| A-11 | Evaluation | Q&A preparation does not exist yet (evaluation goal) | Create docs/13 (plan §6) |
| A-12 | Consistency | Terminology/links spot-check across docs 01–13 not yet done as a final pass | Documentation-verification checklist item (TC-S6-D01) |

## 3. Requirements Traceability Plan (built out in docs/11 at implementation)

Format: one row per requirement —

`Requirement (FR/NFR) → User story → Acceptance criterion → Implementation area → Test ID(s) → Evidence`

Evidence sources that already exist and will be linked: TC-S1-*, TC-S2-*,
TC-S3-*, TC-S4-*, TC-S5-* catalogues in docs/04; the five-invoice
verification runs; the manual acceptance table; security checks.

**Known traceability results to record honestly (no invented evidence):**

| Requirement | Status | Evidence |
|---|---|---|
| FR-1–FR-10, FR-12–FR-16 (Must/Should core) | Covered | Sprint 1–5 test catalogues + five-invoice runs |
| FR-11 / US-8 edit-after-save (Should) | **GAP — deferred** | Decision recorded docs/09 §8 |
| FR-14 date-range filter + sort (Should) | **GAP — partial** (search only) | Sprint 4 scope decision; search evidence TC-S4-I04–I07 |
| FR-17 / US-11 OCR (Could) | **GAP — deferred by gate** | docs/10 §5 decision + evidence |
| FR-18 / US-12 CSV export (Could) | **GAP — not selected** | Plan note (docs/03 Sprint 6 "if selected") |
| NFR-1–NFR-10 | Covered, except NFR-9 re-verification | Security/robustness tests; A-8 re-check planned |

Deferred items stay **visible as deferred** in the matrix — the evaluation
claim is "known, decided, documented", not "done".

## 4. Final Test Strategy

Reuse-first: the 169 existing tests are the regression suite — they are
re-run, not duplicated. New work is only what produces *new* evidence:

| Category | IDs | What | Why it matters |
|---|---|---|---|
| A. Full regression | TC-S6-R01 | Complete suite, clean run, recorded | Final green proof at HEAD |
| B. Real-invoice tests | TC-S6-E01 | Parser verification script vs expected values | Confirms 65/65 still holds at HEAD |
| C. Real-invoice lifecycle | TC-S6-E02 | HTTP lifecycle on the five invoices (reuse Sprint 5 script) | End-to-end proof at HEAD |
| D. Clean-setup verification | TC-S6-S01 | Fresh venv → `pip install -r requirements.txt` → boot → smoke | NFR-9 final evidence (A-8) |
| E. Security re-checks | TC-S6-S02 | Origin 403 / GET-delete 405 / injection search / contained serving / isolation — re-run existing tests | Final security evidence |
| F. Error-path re-check | TC-S6-E03 | No-text gate + known failures replay | Final hardening evidence |
| G. Documentation checks | TC-S6-D01–D04 | D01 links/terminology pass across docs; D02 README accuracy; D03 traceability matrix complete (every FR/NFR row has evidence or a marked GAP); D04 prompt/dev logs complete through Sprint 6 | Documentation is part of the deliverable |
| H. OCR gate | TC-S6-O01 | Decision + evidence present in docs/04, docs/10, README | Gate recorded, no OCR code |
| I. Manual acceptance | TC-S6-M01 | Reviewer walkthrough using docs/13 Q&A + README only (no help from the developer) — evaluation-readiness proof | The docs stand on their own |

## 5. SDLC Evidence Audit (current classification)

| # | Area | Status | Evidence |
|---|---|---|---|
| 1 | Requirements analysis | **PASS** | docs/01 (12 areas, MoSCoW, 25 edge cases) |
| 2 | Exploration | **PASS** | docs/02 + docs/07 (fresh invoice evidence) |
| 3 | User stories | **PASS** | US-1–12 (docs/01), US-S3/S4/S5 series in docs/08–10 |
| 4 | Acceptance criteria | **PASS** | Given/When/Then per story; per-sprint ACs |
| 5 | Architecture | **PASS** | docs/02 §16–18, docs/03, layered implementation as designed |
| 6 | Sprint planning | **PASS** | docs/03 + per-sprint design docs 08–10 |
| 7 | Prompt engineering | **PASS** | docs/05 P-01…P-13 (per-phase, logged before work) |
| 8 | Development logs | **PASS** | docs/06 (dated entries, decisions, incidents) |
| 9 | Test planning | **PASS** | docs/03 §10, per-sprint strategies (docs/08–10 §6) |
| 10 | Test execution | **PASS** | docs/04: per-ID catalogue with verdicts, per-sprint counts |
| 11 | Failure investigation | **PASS** | I-1…I-31 issue log with fixes |
| 12 | Regression testing | **PASS** | per-sprint full-suite gates; history clean |
| 13 | Real-data verification | **PASS** | 65/65 + 23 lines at every sprint since 2 |
| 14 | Security testing | **PASS** | Origin 403, 405, injection, traversal, isolation tests |
| 15 | Git/version control | **PASS** | 6 commits, one per sprint, clean tree, no remote |
| 16 | Retrospective | **GAP → planned** | docs/12 (Sprint 6 deliverable) |
| — | Traceability matrix | **PARTIAL → planned** | docs/11 (A-3) |
| — | Evaluation Q&A | **GAP → planned** | docs/13 (A-11) |

## 6. Evaluation Q&A readiness plan (docs/13)

Questions to prepare (answers drawn from existing documentation where it
already exists — flagged where a fresh concise answer must be written):

- **Claude Code:** what it is; how it was used (per-phase pair-engineer:
  planning, implementation, testing, verification — P-01…P-13 show the
  prompt strategy); planning-vs-implementation separation (phase gates,
  STOP-for-approval discipline); how the project was inspected (code + docs
  + live evidence, never assumptions); failure handling (I-1…I-31 log);
  scope control (MoSCoW, phase gates, documented deferrals); testing approach;
  Git usage; how the SDLC process improved the result (examples: no-text gap
  found by audit, OneDrive incident handled per documented risk).
- **Project:** why Flask / pdfplumber / SQLite / no-ORM / Decimal /
  synchronous local architecture; how validation, extraction, line items,
  review, save-rollback, history, search, safe deletion, isolation work; why
  OCR was deferred; scanned-PDF behavior; current limitations (vendor
  accuracy, single-user, no edit-after-save, deferred FR-11/14/17/18);
  next production improvements.

Existing documentation already answers most of these — docs/13 will index
and condense rather than invent.

## 7. Retrospective plan (docs/12)

Evidence-based outline (no invented experiences): what went well (phase-gate
discipline; test-first catching real defects — e.g., the Sprint 2 NameError
and label-boundary bugs; one-commit-per-sprint history) · what went wrong
(OneDrive DB swap mid-acceptance; disk-full event; orphan servers binding
port 5000; folder-lock archive move; curl `-X POST -L` trap) · debugging
incidents (I-1…I-31 highlights) · lessons (verify environment assumptions;
localhost tools still need operational discipline; logs made every fix
traceable) · what would be done differently · remaining limits · production
improvement list (edit-after-save, filters/sort, OCR tier, backup, packaging).

## 8. Final Definition of Done (Sprint 6)

**Functional:** every pipeline step works and is evidenced (existing tests +
final run); scanned/no-text handling proven; error handling audited.
**Quality:** 169+ tests green at HEAD; security re-checks green; five real
invoices 65/65 at HEAD; isolation and no-raw-exception evidence current;
samples unchanged and git-ignored; clean-venv setup verified.
**SDLC:** all docs 01–13 complete and cross-linked; traceability matrix
complete with honest GAP markings; prompts and dev logs complete through
Sprint 6; failures documented; Git history clean; single Sprint 6 commit
after approval; version tag `v1.0.0` created with approval.
**Evaluation:** docs/12 retrospective + docs/13 Q&A complete; a reviewer can
reconstruct the whole project from the docs alone (TC-S6-M01).

## 9. Files planned (implementation phase)

| File | Change |
|---|---|
| `docs/11-final-verification-plan.md` → final record | planning doc now; gains the final verification evidence + traceability matrix |
| `docs/12-retrospective.md` | **new** at implementation |
| `docs/13-evaluation-q-and-a.md` | **new** at implementation |
| `docs/04-test-results.md` | Sprint 6 final run records |
| `docs/05`, `docs/06` | prompt + dev log entries |
| `README.md` | A-1/A-2 fixes; final status |
| `CHANGELOG.md` | 1.0.0 entry |
| Git | one Sprint 6 commit + `v1.0.0` tag (both with approval) |

No application source changes are planned. If finalization uncovers a defect,
it will be reported and handled as a stop-and-report per process.

## 10. Risks

| # | Risk | Mitigation |
|---|---|---|
| R-S6-1 | Clean-venv re-setup hits the disk/OneDrive environment issues seen earlier | Check free space first; reuse the recorded workaround; stop-and-report if blocked |
| R-S6-2 | Traceability matrix exposes more gaps than A-4–A-7 | That is its purpose — gaps are recorded honestly as deferred/decided, not back-filled |
| R-S6-3 | Docs drift while writing 11–13 | Final link/terminology pass (TC-S6-D01) happens last |

## 11. Scope exclusions

Everything in the Sprint 5 exclusion list stays excluded (auth, cloud,
multi-user, analytics, AI, OCR, bulk ops, export, email, new DB engine,
edit-after-save, new management features, UI redesign). Sprint 6 adds **no
features** — verification, evidence, and documentation only.

---

# FINAL VERIFICATION RESULTS (Sprint 6 execution, 2026-10-06)

All checks below were executed at HEAD `d22b855`. Existing Sprint 0–5
evidence is reused where valid and cited; nothing was re-invented.

## Final verification record

| ID | Check | Result | Evidence |
|---|---|---|---|
| TC-S6-R01 | Full regression suite at HEAD | **169 passed / 0 failed / 0 skipped** | `pytest -q` run this sprint |
| TC-S6-E01 | Five-invoice parser verification | **ALL 5 PASS — 65/65 field checks**, 23/23 line items, consistency checks green | re-run output this sprint |
| TC-S6-E02 | HTTP lifecycle on the five invoices (upload→extract→review→save→history+search→detail→original) | **ALL 5 PASS**, every step | acceptance script output |
| TC-S6-S01 | NFR-9 clean-setup: fresh venv → `pip install -r requirements.txt` → full suite → boot | **PASS**: install exit 0, **169 passed** with the clean venv, boot HTTP 200 | this sprint |
| TC-S6-S02 | Security re-verification | **PASS** | TC-S3-I18 (Origin 403), TC-S4-I16 (GET-delete 405), TC-S4-I20 (contained serving), TC-S4-I18/I07 (injection/literal), TC-S5-I04/I05 (isolation) — all green in the R01 run |
| TC-S6-E03 | No-text / OCR gate behavior | **PASS** | TC-S5-U01/U02, TC-S5-I01 green in R01; gate decision docs/10 §5 |
| TC-S6-D01 | Documentation links/terminology pass | **PASS** (docs 01–13 cross-checked; FR-numbering erratum noted below) | this sprint |
| TC-S6-D02 | README accuracy | **PASS** after fixes (A-1/A-2 applied: Tesseract prerequisite updated to the NO-GO decision; docs table complete; status table final) | README diff |
| TC-S6-D03 | Traceability matrix complete | **PASS** — every FR/NFR row classified; 4 honest GAP/DEFERRED markings preserved | matrix below |
| TC-S6-D04 | Prompt/dev logs complete | **PASS** — P-01…P-14 cover every phase including this one; dev log has dated entries per sprint incl. incidents | docs/05, docs/06 |
| TC-S6-O01 | OCR gate recorded | **PASS** — NO-GO/deferred with evidence in docs/04, docs/10 §5, README | docs/04 Sprint 5 section |
| TC-S6-M01 | Reviewer walkthrough (docs only) | **PASS with notes** — see walkthrough result below | this sprint |

**Walkthrough result:** a reviewer using only the documentation can
reconstruct all 13 walkthrough points (objective, architecture rationale,
per-sprint builds, Claude Code usage, prompt strategy, failures+fixes,
testing, real-invoice verification, security checks, exclusions, limitations,
production improvements). Remaining gap: none blocking; the deferred items
are documented as decisions rather than omissions.

**Erratum (cross-reference correction):** docs/09 §8 cited "FR-14" for
search/filter/sort — per docs/01 the correct id is **FR-13** (search/filter/
sort; FR-14 is duplicate warnings). The matrix below uses the correct ids;
docs/09 is preserved as written with this erratum noted here.

## Requirements traceability matrix (final)

Classification: **PASS** (evidenced) · **PARTIAL** (some evidence) ·
**DEFERRED** (decided, documented) · **GAP** (no evidence — none remain unexplained).

| Requirement | User story | Acceptance criteria | Implementation | Test IDs | Evidence | Class |
|---|---|---|---|---|---|---|
| FR-1 Upload | US-1 | AC-1.1–1.4 | routes/uploads.py, services/uploading.py | TC-S1-U01–U03, I01 | docs/04 S1 | PASS |
| FR-2 Validate | US-1/US-7 | AC-1.2–1.4, AC-7.1 | uploading gates 1–6 | TC-S1-U02–U15, I02–I06; TC-S5-I03 | docs/04 S1/S5 | PASS |
| FR-3 Safe storage | US-1 | AC-1.1 | uploading UUID storage + hash | TC-S1-U01/U13/I01/I07 | docs/04 S1 | PASS |
| FR-4 Extract text | US-2 | AC-2.1 | services/extraction.py + pdfplumber | TC-S2-E01–E05; TC-S6-E01 | docs/04 S2/S6 | PASS |
| FR-5 Parse fields | US-2 | AC-2.1–2.3 | services/parser/* | TC-S2-F01–F14, L01–L05, E01–E05 | docs/04 S2 | PASS |
| FR-6 Status display | US-2/US-3 | AC-2.2, AC-3.1 | parser Field model + review flags | TC-S2-F12/F13; TC-S3-I03 | docs/04 S2/S3 | PASS |
| FR-7 Review & correct | US-3 | AC-3.1–3.4 | routes/invoices review + services/review | TC-S3-I03/I04/I08 | docs/04 S3 | PASS |
| FR-8 Atomic save | US-4 | AC-4.1–4.3 | repository.save_invoice | TC-S3-I04, I11 (rollback), I12 (guard) | docs/04 S3 | PASS |
| FR-9 List saved | US-5 | AC-5.1 | routes/invoices history + list_saved | TC-S4-I01/I01b | docs/04 S4 | PASS |
| FR-10 Detail + original | US-6 | AC-6.1–6.2 | detail route + original serving | TC-S4-I08/I20 | docs/04 S4 | PASS |
| FR-11 Edit saved (Should) | US-8 | — | **not implemented** | — | docs/09 §8 decision | **DEFERRED** |
| FR-12 Delete | US-9 | AC-9.1–9.2 | delete route + service | TC-S4-I11–I15 | docs/04 S4 | PASS |
| FR-13 Search/filter/sort (Should) | US-10 | AC-10.1–10.2 | history q search | TC-S4-I04–I07 | docs/04 S4 | **PARTIAL** — search PASS; date-range filter + user sort **DEFERRED** (Sprint 4 scope) |
| FR-14 Duplicate warnings (Should) | US-4 | AC-4.2 | upload flash + save 409 gate | TC-S1-U16/I08; TC-S3-I14/I15 | docs/04 S1/S3 | PASS |
| FR-15 Error states (Must) | US-7 | AC-7.1–7.2 | gate messages + failed status | TC-S1-I02–I06; TC-S5-I03 | docs/04 S1/S5 | PASS |
| FR-16 Normalization (Should) | US-2 | AC-2.4 | parser/normalize.py | TC-S2-N01–N27 | docs/04 S2 | PASS |
| FR-17 OCR (Could) | US-11 | AC-11.1–2 | **not implemented** — gate NO-GO | TC-S5-U01/I01 (graceful path) | docs/10 §5 | **DEFERRED** |
| FR-18 CSV export (Could) | US-12 | AC-12.1 | **not implemented** | — | plan note | **NOT SELECTED** |
| FR-11 supplement: scanned handling | US-7 | AC-7.1 | no-text gate (Sprint 5) | TC-S5-U01, I01 | docs/04 S5 | PASS |
| NFR-1 Locality | — | — | 127.0.0.1 binding, offline assets | TC-S1-I10 | docs/04 S1 | PASS |
| NFR-2 Privacy | — | — | git-ignore + containment | git checks; TC-S4-I20 | docs/04 | PASS |
| NFR-3 Performance | — | — | ≤5 s extraction observed | manual acceptance timings | docs/04 S5 | PASS |
| NFR-4 Reliability | — | — | error-path audit | TC-S5-I03 | docs/04 S5 | PASS |
| NFR-5 Integrity | — | — | transactions + cascade | TC-S3-I11; TC-S4-I13/U11 | docs/04 S3/S4 | PASS |
| NFR-6 Usability | — | — | review flow + messages | manual acceptance | docs/04 S5 | PASS |
| NFR-7 Maintainability | — | — | layering + pure parser | suite structure | docs/02/03 | PASS |
| NFR-8 Testability | — | — | 169 tests, temp-DB isolation | suite | docs/04 | PASS |
| NFR-9 Portability | — | — | clean-venv setup | **TC-S6-S01** | docs/11 §results | PASS |
| NFR-10 Capacity | — | — | minimal pagination design | TC-S4-I21 | docs/04 S4 | PASS |

**Summary: 24 PASS · 1 PARTIAL (FR-13: search PASS, filter/sort deferred) ·
3 DEFERRED (FR-11, FR-17, FR-18) · 0 unexplained GAPs.**
