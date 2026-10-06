# 06 — Development Log

Dated build journal. Newest at the bottom. Companion to the prompt log
([05-prompt-log.md](05-prompt-log.md)).

---

## 2026-10-06

**Phase 1 — Requirements analysis (complete).**
Wrote [01-requirements-analysis.md](01-requirements-analysis.md): problem
statement, single-user persona + 5 use cases, 18 functional requirements
(MoSCoW), 10 NFRs, 12 user stories with Given/When/Then acceptance criteria,
25 catalogued edge cases, 7 risks, 11 security/privacy points, assumptions,
and 9 open decisions with recommendations. **User approved.** Notable scope
calls for the one-day deadline: PDF-only v1 (images+OCR gated together), no
cloud-LLM extraction (locality promise), error clarity promoted to a Must
story. Before writing, a previous 2026-10-05 partial project was discovered
nested in the workspace; per user choice it was left untouched and the fresh
start reopened all decisions.

**Phase 2 — Exploration (complete).**
Verified the environment first: Python 3.14.7, pip 26.2.1, git 2.55 present;
**Tesseract not installed** — material to the OCR decision. Wrote
[02-exploration.md](02-exploration.md): compared 4 overall approaches
(recommended Flask server-rendered + rules parser + SQLite), selected
pdfplumber with a two-view extraction design (plain text + words-with-
coordinates for label→value geometry), defined the per-field status model
(found/ambiguous/missing + source), the preference-ordered total strategy,
SQLite schema with status lifecycle, synchronous in-request extraction,
ordered upload gates, and the testing strategy. **User approved all decisions
T-A…T-J**, including: PDF-only Must scope, sqlite3 without ORM, Decimal-at-
boundaries money, Origin-check CSRF, 10 MB / 50-page limits, OCR gated on a
mid-plan checkpoint, and careful (non-destructive) handling of the old folder.

**Phase 3 — Planning (complete — approved by user).**
Wrote [03-plan.md](03-plan.md): final directory structure, component
responsibility table (one-way dependencies, pure parser), finalized schema,
16-step data flow with failure branches, story→sprint mapping, seven sprints
for today (S0 foundation → S6 final review) with time boxes and a gated
optional OCR spike, task breakdown per sprint (~45 tasks), test categories
(~105 planned cases), documentation set, git checkpoint rules, per-sprint and
final Definitions of Done. Three manual items flagged for the user: **M-1**
approve archiving the old folder before `git init` (verified: it contains no
data — nothing to copy, history preserved by moving intact), **M-2** supply
real sample invoices for tuning, **M-3** confirm money storage (REAL +
Decimal recommended). Prompt log and this journal seeded.

**Sprint 0 — Foundation (started).**
Plan [03-plan.md](03-plan.md) approved together with all manual items: **M-1**
archive the old folder as a move (never delete, git history preserved),
**M-2** user will supply 3–5 real invoice PDFs (never committed to git),
**M-3** money as REAL columns + `decimal.Decimal` at application boundaries.
Prompt log updated (P-04) before any changes, per the user's instruction.
Scope discipline for this sprint: scaffold only — no upload gates, no
extraction, no parser (those belong to Sprints 1–2). Exit criteria: smoke
tests green, server verified on 127.0.0.1, structure matches plan §1, first
commit made.

**Sprint 0 — Foundation (complete).**
All exit criteria met. M-1 executed as a move: the old folder's *contents*
(including `.git`) went to `../invoice-extractor-archive-2026-10-05/` — the
folder handle was held by another program, so contents were moved one by one,
history verified intact (commit `f518ca8`), and the empty shell removed.
Nothing was deleted. Structure created per plan §1; venv + pinned deps
installed cleanly on Python 3.14 (risk T-2 retired); app factory, config
(localhost-only, 10 MB / 50 pages), idempotent schema with M-3 money
documentation delivered. Smoke tests 3/3 green in 0.20 s; real-server boot
verified (HTTP 200, 127.0.0.1 binding, DB created). First commit `72b30cb`;
working tree clean. Results recorded in
[04-test-results.md](04-test-results.md) (issues I-1–I-3 noted there). No
later-sprint features were built. Ready for Sprint 1 (upload & store) on the
user's go-ahead; awaiting sample invoices (M-2) by Sprint 2.

**Sprint 1 — Upload & secure file storage (started).**
Prompt P-05 logged first per user instruction. Scope: upload gates
(presence → extension → size → magic bytes → open/encryption/page-count),
UUID-based safe storage with single-pass SHA-256, repository functions,
upload page with flash feedback and recent-uploads panel, non-blocking
hash-duplicate warning (save-time vendor+number check belongs to Sprint 3
per plan §4 step 14), Flask 413 handler for the size backstop, and the
unit/integration test catalogue (TC-S1-*). Explicitly out of scope: any
extraction or parsing — status remains `uploaded` after this sprint.

**Sprint 1 — Upload & secure file storage (complete).**
Tasks S1-T1…T7 delivered. **Implementation:** `services/uploading.py` runs the
gate sequence (presence → extension → size → 5-byte `%PDF-` magic →
openability/encryption → 50-page cap) and stores files as `<uuid-hex>.pdf` with
a single-pass SHA-256; `db/repository.py` owns all SQL (parameterized only);
`routes/uploads.py` serves the upload page + `POST /upload` with flash
feedback and a recent-uploads panel; a 413 errorhandler translates Flask's
`MAX_CONTENT_LENGTH` rejection into the same friendly message; home-page UI
replaced the Sprint 0 placeholder. **Decisions:** upload-time duplicate check
is hash-only and *non-blocking* (informational warning, FR-15) — the blocking
confirm-with-override belongs to save time (Sprint 3, AC-4.2), per plan §4
step 14; upload bodies ≤10 MB are read into memory for simplicity and
single-pass hashing; rejected uploads store nothing (no file, no row); the
client filename is never used for paths and never echoed in messages.
**Verification:** full suite **30 passed / 0 failed / 0 skipped**; manual
verification on a real server covered success, magic-byte rejection, duplicate
warning, safe storage, and clean shutdown (TC-S1-M01…M05 in
[04-test-results.md](04-test-results.md)); synthetic manual-test data removed
afterward. **Issues:** orphaned Flask processes double-bound port 5000 and
produced phantom 500s — killed by PID; session-cookie requirement for flash
visibility over curl; a handful of test defects fixed before green (I-4…I-7).
**Scope kept:** no extraction or parser code — that is Sprint 2. Commit:
`sprint-1` (see git log for hash).

**Sprint 2 — Invoice extraction & parser (started).**
Prompt P-06 logged first. M-2 fulfilled: five real sample PDFs now in
`sample_invoices/` (git-ignored, verified). Process mandated by the user:
**Phase A** real-invoice exploration with pdfplumber before any parser code
(document every field actually present — no assumptions), **Phase B** parser
design from findings, **Phase C** implementation plan then code, **Phase D**
tests asserting exact expected values derived from the real contents,
**Phase E** verification with per-invoice extracted results and field-level
accuracy. Findings and design to be recorded in docs/07-invoice-exploration.md.
OCR stays out unless exploration proves it necessary (Tesseract unavailable).
Scope: extraction/parser only — no review UI, save flow, or management.

**Sprint 2 — Invoice extraction & parser (complete).**
Phases executed as mandated. **A — exploration first:** all five samples
inspected with pdfplumber before any parser code; findings recorded in
[07-invoice-exploration.md](07-invoice-exploration.md). The real invoices
changed the design in five ways: currency glyph corrupts to 'n' (→
evidence-based INR inference, flagged ambiguous), dates are DD-Mon-YYYY, no
due date exists ("Payment: Due on receipt" must not parse as one), discount +
GSTIN + bill-to fields exist (→ schema gained `discount`, `vendor_tax_id`,
`bill_to` via idempotent boot migration), and totals live inside the item
table (→ item/summary row separation). **B/C — design & plan** documented in
docs/07 §Phase B/C before coding. **Implementation:** pure parser package
(normalize / labels / fields / lines / parse with per-strategy containment),
`services/extraction.py` (two-view → parse → atomic persist, status
extracted/failed), repository `update_extraction`, upload route wired to
extract in-request. **Testing:** 58 new cases; expected values asserted
exactly against exploration transcriptions. **Verification:** full suite
**88/0/0**; field-level accuracy **65/65 header fields (incl. 5
ambiguous-flagged currency), 23/23 line items, 10/10 consistency checks**.
**Issues:** seven real parser bugs caught and fixed during bring-up (mid-line
labels, GSTIN/gst collision, rate-into-amount merge, Subtotal/total prefix
collision, tuple double-unpack, eager vendor fallback, containment
double-wrap) plus one refactor NameError the suite caught (I-8…I-17 in
docs/04). **Scope kept:** no review UI, no save workflow, no management
features — Sprint 3. Samples remain git-ignored (verified). Commit: see git
log `sprint-2`.
