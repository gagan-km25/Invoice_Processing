# 13 — Evaluation Q&A

Sprint 6 deliverable · 2026-10-06. Concise, technically accurate answers based
on the actual implementation and documentation. Cross-references point to the
evidence.

---

## Part 1 — Claude Code

### What is Claude Code?
Claude Code is an agentic coding assistant (CLI / IDE extension) that can
read and edit files, run shell commands, run tests, and work with Git inside
a project directory. In this project it acted as the sole implementer while
the human owner approved every phase gate.

### How was Claude Code used in this project?
End to end, under a gated SDLC (prompt log: docs/05, P-01…P-14): it wrote the
requirements analysis, explored the problem and the real invoices, produced
per-sprint designs, implemented all six sprints, wrote and ran the 169-test
suite, performed manual acceptance runs against a live server, maintained
nine documentation files, and operated Git (one commit per sprint, always
after explicit approval). Every sprint ended with an evidence report and a
STOP for human approval before the next phase.

### Planning vs implementation — how were they kept separate?
Each sprint had two distinct phases with an approval gate between them: a
planning phase (design documents in docs/08–10, explicitly "no code") and an
implementation phase (code + tests only within the approved design). If
planning revealed a scope conflict (e.g., Sprint 4's edit-after-save), it was
reported and resolved by the owner before implementation started.

### How were prompts structured?
Each prompt stated the phase, the exact scope, the process requirements
(logs first, no future-sprint work), the required verification, and the
required stopping point. The prompt log (docs/05) records the intent of every
prompt, the artifacts it produced, and any course corrections.

### How did Claude Code inspect the project?
File reads, Git history/status queries, targeted `grep`, live PDF inspection
with pdfplumber (the Sprint 2/5 invoice exploration), and live HTTP checks
against a running server. Verification was always against real artifacts —
e.g., the OCR gate re-inspected all five invoices rather than assuming.

### How were failures and debugging handled?
Every failure was investigated, fixed, re-tested, and logged with an ID
(I-1…I-31 in docs/04). Examples: orphan Flask servers double-binding port
5000 (diagnosed via `netstat`, fixed by killing OS PIDs); a parser label
collision turning `GSTIN` digits into a tax amount (fixed with word-boundary
label matching); a mid-refactor NameError caught by the suite.

### How was scope controlled?
MoSCoW tiers per sprint, explicit exclusion lists in every design doc,
Should/Could items implemented only if approved, and honest GAP/DEFERRED
markings in the traceability matrix (docs/11 §matrix) instead of silent scope
expansion. One scope conflict (edit-after-save) was escalated and deferred.

### How was testing performed?
pytest with stable test IDs (TC-S1…TC-S5): unit tests for pure logic
(parser, validation, repository), integration tests over HTTP with temporary
databases, an error-path audit, security tests, and scripted real-invoice
acceptance runs against a live server. Full regression gated every commit.
See docs/04 for per-ID expected/actual/verdict records.

### How was Git used?
Local repository, no remote. One commit per sprint, each gated on a green
suite and created only after human approval; clean tree between sprints; a
`v1.0.0` tag at completion. Data directories and real invoices are
git-ignored (verified every sprint).

### How did the SDLC process improve the result?
Concrete examples: the Sprint 5 planning audit found the no-text-layer gap
that implementation had missed; the Sprint 4 approval gate surfaced and
deferred edit-after-save explicitly instead of by implication; the traceability
audit produced honest GAP markings (edit, filter/sort, OCR, export) rather
than inflated claims; and per-sprint regression gates caught every regression
the moment it appeared.

---

## Part 2 — Project

### Why Flask?
Server-rendered HTML fits the workflow (upload → review → save are forms);
Flask is lightweight with no build step; Python gives one language for web +
PDF parsing + tests. Alternatives rejected: FastAPI (pulls toward an SPA
split), Django (too much for a local tool), Node (weaker PDF ecosystem),
desktop GUI (the requirement was a web app). docs/02 §1.

### Why pdfplumber?
Best balance of text fidelity, table extraction, and word-coordinate access
(the "two-view" design needs geometry, not just text), pure-Python install,
MIT license. pypdf loses layout; PyMuPDF is faster but AGPL; poppler needs a
system binary. docs/02 §3.

### Why SQLite? Why no ORM?
Zero-install, single-file, ideal for one local user; the schema is small and
stable, so a thin repository layer with parameterized SQL is simpler and more
transparent than an ORM. `PRAGMA foreign_keys = ON` per connection powers
cascade deletes. docs/02 §7, docs/03 §3.

### Why Decimal?
SQLite has no decimal type; floats drift. All money is parsed, validated,
and compared with `decimal.Decimal` (quantized to 0.01) at the application
boundary and stored as REAL — one documented representation (docs/09, M-3).

### Why a synchronous local architecture?
One user, files ≤10 MB, ≤50 pages, extraction ≤5 s — a background job queue
would add complexity with no payoff. Guarded by size/page caps. docs/02 §10.

### How does upload validation work?
An ordered gate sequence: request size cap → presence → `.pdf` extension →
`%PDF-` magic bytes → pdfplumber openability (encryption, page count ≤ 50) →
store under a server-generated UUID name with SHA-256 hashing. Every rejection
stores nothing and explains exactly why. docs/02 §12.

### How does extraction work? How are line items extracted?
Two views per page: plain text (regex) and words-with-coordinates (geometric
label→value lookup), plus `extract_tables()` for line items. Fields are found
by label dictionaries with preference ordering and word-boundary matching,
then normalized (ISO dates, Decimal amounts, currency) with a per-field
status of found/ambiguous/missing. A crash in one strategy marks that field
missing — never the whole parse. docs/07 §6.

### How is extracted data reviewed and validated before saving?
A review form pre-fills every field from the extraction draft, flags
ambiguous/missing fields, and validates entirely server-side: required
fields, decimal quantization, strict dates, quantity > 0, currency format.
Warnings (due < invoice, amount ≠ qty × unit, totals mismatch) are shown but
never block — wrong-looking-but-valid input is the user's call. docs/08 §4.

### How is the SQLite transaction / rollback handled?
`save_invoice` guards `status='extracted'`, then in one transaction updates
the header, deletes the old lines, inserts the submitted lines, and commits.
Any exception rolls back and re-raises — verified by a test that injects a
failure on the line INSERT and asserts the header and prior lines are
untouched. docs/09 (TC-S3-I11).

### How do history and search work?
`list_saved` filters `status='saved'`, orders by invoice date desc (id
tiebreak), supports a search box across invoice number and vendor using an
escaped parameterized LIKE (`%`/`_` literal, case-insensitive), paginated at
50 per page with a count. docs/09.

### How is deletion handled safely?
POST-only, behind a confirmation step (nothing deletes on the first
request), guarded to `saved` records only, covered by the Origin check; line
items cascade via a foreign key with `PRAGMA foreign_keys = ON`, verified
zero-orphan in tests; the stored file is removed best-effort with missing-
file tolerance. docs/09.

### How is invoice isolation enforced?
Every page is rendered from a single record fetched by id; drafts live
server-side keyed by that id; tests assert no cross-appearance of values
between two invoices' review/detail/history pages (TC-S5-I04/I05).

### Why was OCR deferred? What happens with scanned PDFs?
Gate evidence (docs/10 §5): all verified invoices are text-based, pdfplumber
is proven sufficient, Tesseract is not installed, and OCR would add a system
dependency plus a second extraction path for zero current invoices. Scanned
PDFs are detected (no selectable text) and fail with "likely a scan" plus
guidance — instead of silently producing an empty extraction.

### What are the current limitations?
Single-user, localhost, DEBUG server by design; vendor extraction is
heuristic and always flagged; edit-after-save deferred; search without
date-range filter or sort controls; OCR deferred; accuracy proven on five
layouts; data lives in one SQLite file with no backup tooling. docs/12.

### What would production improvements look like?
Edit-after-save; filters/sort; an OCR tier behind the existing extractor
interface; packaging and migrations; background extraction; backup/export;
structured logging; authentication if multi-user. docs/12 §production.
