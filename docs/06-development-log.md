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
