# 02 — Exploration & Technical Analysis

Phase: **Exploration** (after approved requirement analysis, before planning).
Date: 2026-10-06 · Status: **DRAFT — awaiting user approval**
Purpose: determine *how* to build the Invoice Extractor. No code, no project
files — analysis and recommendations only. Requirement references are to
[01-requirements-analysis.md](01-requirements-analysis.md).

---

## 0. Environment Findings (verified on this machine, 2026-10-06)

| Check | Result | Consequence |
|---|---|---|
| Python | 3.14.7 (`C:\Python314`), pip 26.2.1 | Stack must support 3.14; virtualenv + `pip install` verified in Sprint 0 |
| Tesseract OCR | **Not installed** | OCR needs a system-level install (friction). Confirms OCR stays a gated bonus tier |
| Git | 2.55 available | Local repo ready; old `invoice-extractor/` folder must be moved out before `git init` (see Decisions) |
| Folder location | Inside OneDrive sync | SQLite locking risk (R-4) is real here; mitigations below |

---

## 1. Comparison of Overall Approaches

| | **A. Flask server-rendered + rules parser + SQLite** | B. FastAPI + SPA (React/Vue) | C. Node.js full-stack | D. Local LLM extraction (Ollama) |
|---|---|---|---|---|
| Setup time today | Low — no build step, no frontend toolchain | High — API + SPA + bundler | Medium — but see extraction | High — multi-GB model download |
| PDF/OCR ecosystem | **Best** (pdfplumber etc.) | Same (Python) | Weak (thin wrappers, poor table support) | Bypasses parsing, but slow, non-deterministic, untestable |
| Offline / privacy | **Fully** | Fully | Fully | Fully (after big download) |
| Testability | **Pure-function parser + Flask test client** | Good | Good | Poor (output varies run to run) |
| Fit to workflow | **Upload → review → save is exactly HTML forms** | Over-engineered for 1 user | — | — |
| Risk for one-day build | Low | High | Medium-high | High |

**Recommendation: Approach A.** The decisive arguments: (1) Python owns the PDF
extraction ecosystem; (2) for a single local user, server-rendered forms beat an
API+SPA — fewer moving parts, no build step, works offline; (3) a rules parser is
deterministic and unit-testable, which an LLM approach is not. The extractor stays
behind one interface (R-1 mitigation), so B/D remain possible later without
touching routes or storage.

---

## 2. File Formats to Support (Q1)

| Option | Assessment |
|---|---|
| **PDF (text layer)** — v1 core | The dominant invoice format; one extraction path; fully covered by pure-Python libraries |
| Scanned PDF (image-only) | Needs rasterizing + OCR; Tesseract not installed → system install friction; accuracy image-quality-dependent |
| JPG / PNG images | OCR-only path; same friction as above |
| DOCX / XLSX / e-invoices (UBL etc.) | Out of scope v1 (per requirements §2) |

**Recommendation:** **PDF only for the Must tier.** Handle "PDF with no text
layer" as a *detected condition* with a specific message (see §13) rather than
silently attempting OCR. JPG/PNG + OCR is one coherent bonus tier (US-11/FR-17),
gated on the mid-afternoon checkpoint and a Tesseract install.

---

## 3. Extracting Text from Text-Based PDFs (Q2)

| Library | Text fidelity | Tables | Install | License | Notes |
|---|---|---|---|---|---|
| **pdfplumber** (chosen) | Good, layout-aware; exposes words/chars with coordinates | **Yes** (`extract_table`) | Pure Python, pip-only | MIT | Built on pdfminer.six; slower than PyMuPDF but fine at ≤10 MB / local scale |
| pypdf | Weaker layout fidelity | No | Pure Python | BSD | Fine for plain text, loses geometry we want |
| PyMuPDF (fitz) | Excellent, fastest | Partial | Binary wheel | **AGPL** | Speed unneeded at this scale; license worth avoiding in a portfolio piece |
| poppler `pdftotext` | Good | No | External binary | — | System install friction; reject |

**Recommended: pdfplumber.** The key design insight: use **two views of every page**:

1. `page.extract_text()` — plain text for regex matching (amounts, dates, labels);
2. `page.extract_words()` — words **with coordinates**, for *geometric* label→value
   matching: find a label word ("Invoice", "Total"), then take the nearest value to
   its right on the same line (or directly below) — this handles the common
   `Label .......... value` and columnar layouts far better than regex alone.

Table extraction (`extract_table`) is the first attempt for line items, with a
heuristic fallback of "ignore lines if no recognizable table" (AC-2.3).

For the OCR tier only: rasterize pages to images with **pypdfium2** (pip-only,
permissive license) → PIL image → Tesseract.

---

## 4. OCR for Scanned / Image Invoices (Q3) — bonus tier

| Option | Assessment |
|---|---|
| **Tesseract + pytesseract** (recommended if tier happens) | The standard; good accuracy on clean 300 DPI scans; needs one-time Windows install (UB-Mannheim installer / winget); per-page seconds |
| EasyOCR / PaddleOCR | pip-installable but pull multi-hundred-MB/torch-sized dependencies and download models on first run — kills the one-day, no-heavy-downloads constraint |
| Cloud OCR APIs | Violates the locality promise (NFR-1/2). Rejected |

Design if attempted: OCR availability probed at startup; scanned PDF → rasterize
(pypdfium2) → `pytesseract.image_to_string` → *same parser* as the text path.
OCR text is noisier and lacks reliable geometry → every OCR-derived field is
flagged `source=ocr` (AC-11.1). Tesseract missing → clear message, no crash
(AC-11.2). **Default expectation for today: this tier does not happen; the
graceful "no text layer" message does.**

---

## 5. Fields to Extract (Q4)

**Header:** vendor · invoice number · invoice date · due date · currency ·
subtotal · tax amount (+ rate if present) · total.
**Line items:** description · quantity · unit price · line amount.
**Record metadata:** status, per-field extraction status (below), SHA-256 file
hash, original filename, stored filename, page count, timestamps, error message.

Honest difficulty ranking (drives where review effort goes):
`total ≈ invoice# < dates ≈ amounts < currency < tax < line items < vendor`.
**Vendor is the hardest** — it usually has no label; it is the letterhead. Best
heuristic: most prominent text (largest font, via pdfplumber char data) in the
top region of page 1, excluding boilerplate keywords ("Invoice", "Date", address
fragments). Vendor will frequently need manual entry — by design it is flagged
low-confidence and the review form makes that a one-click fix, not a failure.

---

## 6. Field Identification & Validation (Q5)

One parser pipeline, pure functions (text-in → structured draft out — unit-testable
without Flask or files):

```
normalize text (whitespace, ligatures, hyphenation breaks)
→ per-field strategies, in order:
    1. label dictionary + same-line capture   ("Invoice No: INV-0042")
    2. geometric fallback (words+coords)      (value right of / below label)
    3. pattern inference                      (date-like / amount-like tokens)
→ per-candidate validation → pick best candidate or mark ambiguous
→ normalization (ISO dates, 2-dp decimals, currency code)
→ cross-field consistency checks
```

| Field | Identification | Validation |
|---|---|---|
| Invoice number | Labels: "Invoice # / No / Number / Reference" → token `[A-Z0-9][A-Z0-9\-/]{2,}` | Single token, sane length, no spaces |
| Invoice date | Labels: "Invoice Date / Date of Issue / Date" | Parses in known formats (US, ISO, "Mar 4, 2025", "4 Mar 2025"); plausible range (1970–now+small margin); ambiguous numeric formats → **flagged, not guessed** (AC-2.4) |
| Due date | Labels: "Due Date / Payment Due / Due by" | Same as invoice date; ≥ invoice date when both present (flag if violated, save allowed) |
| Subtotal | Labels: "Subtotal / Sub-total / Net Amount" | Parses as decimal, ≥ 0 |
| Tax | Labels: "Tax / VAT / Sales Tax / GST"; optional rate ("5%") | Parses as decimal; rate sanity 0–30% |
| Total | Labels **in preference order**: "Total Due / Amount Due / Balance Due" > "Grand Total" > "Total" (multiple "Total"s on a page are the classic trap — E-11) | Parses; ≥ 0; consistency: `subtotal + tax ≈ total` (± 0.01) else **flag**, save still allowed (E-16) |
| Currency | ISO code near amounts ("USD") > symbol on amounts ($, €, £) > "Currency:" label | Mapped to ISO code; none found → empty + flag (never silently assumed) |
| Vendor | Letterhead heuristic (largest font, top of page 1, boilerplate excluded) | Always flagged low-confidence unless an explicit "From/Vendor" label exists |
| Line items | `extract_table` on page(s); header-row keywords ("Qty", "Price", "Amount") | Rows with ≥ description + one numeric column; rows failing validation dropped with a review flag (E-15) |

**Per-field status model** (this is what makes review trustworthy — FR-6):
`found` · `ambiguous` (multiple candidates / ambiguous format) · `missing` — plus
`source`: `text` / `ocr` / `user`. Rules: never mark a guess as `found`; an
`ambiguous` value may be pre-filled but must be visually flagged (AC-3.1);
`missing` renders empty.

---

## 7. Database Design (Q6)

**SQLite via Python's built-in `sqlite3`** — zero install, single file, ideal for
one local user. Alternatives rejected: Postgres/MySQL (server install, pointless
here), JSON files (no querying, no integrity), NoSQL (overkill), ORMs (a thin
repository layer is simpler and more instructive — decision point below).

```sql
CREATE TABLE invoices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  file_hash TEXT NOT NULL,            -- SHA-256, indexed (NOT unique: warn-and-override, D-E)
  original_filename TEXT NOT NULL,
  stored_filename TEXT NOT NULL,      -- server-generated UUID name
  vendor TEXT, invoice_number TEXT,
  invoice_date TEXT, due_date TEXT,   -- ISO 8601 strings
  currency TEXT,
  subtotal REAL, tax REAL, tax_rate REAL, total REAL,
  status TEXT NOT NULL CHECK (status IN ('uploaded','extracted','saved','failed')),
  extraction_json TEXT,               -- per-field status/source draft (resumable review, E-21/E-22)
  error_message TEXT,
  page_count INTEGER,
  created_at TEXT, updated_at TEXT
);
CREATE TABLE invoice_lines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
  line_number INTEGER, description TEXT,
  quantity REAL, unit_price REAL, amount REAL
);
CREATE INDEX idx_invoices_hash ON invoices(file_hash);
CREATE INDEX idx_invoices_number ON invoices(invoice_number);
```

Points that matter:
- **Status lifecycle** `uploaded → extracted → saved` (+ `failed` with reason) makes
  every upload queryable and review resumable (D-009's good idea, restated on merit).
- **Schema created idempotently on boot** → zero-setup first run.
- `PRAGMA foreign_keys = ON` per connection (SQLite default is off!) — deletes cascade.
- **Money representation — decision point:** parse and validate with Python
  `decimal.Decimal`; store as `REAL` (simple; adequate at 2-dp display scale) and
  re-quantize through `Decimal` on read for comparisons. The "correct" alternative
  is INTEGER cents (exact, but adds conversion friction everywhere). Recommendation:
  **Decimal-at-boundaries + REAL storage** for today; note the upgrade path.
- OneDrive risk mitigation: short-lived connections (`open` per operation, no
  long-held handles), small transactions, README guidance to pause sync if DB
  errors appear (R-4).

---

## 8. Backend Technology (Q7)

**Flask** (see §1 comparison). Concretely: app-factory pattern, blueprints for
`uploads` and `invoices`, server-side sessions only for flash messages. The
backend owns all state — the extracted draft lives in SQLite, not in the browser,
which is what makes refresh-mid-review safe (E-22) and review resumable (E-21).

Rejected: FastAPI (pulls toward SPA+API split, no benefit), Django (too much
batteries for a one-day tool), Node (weak PDF ecosystem), GUI toolkits (requirement
is a web app).

## 9. Frontend Technology (Q8)

**Jinja2 server-rendered templates + one hand-written CSS file + a small amount of
vanilla JS** (confirmation dialogs only). Everything works as plain HTML forms —
JS is progressive enhancement, so there is no client-side state to lose. No CDN
assets (NFR-1: works offline), no Tailwind/React build step. Pages: upload/home ·
review · list · detail · edit (reuses review form). Print-friendly detail page is
free via CSS if time allows.

## 10. How the Pieces Communicate (Q9)

```
Browser ──HTTP──> Flask routes (thin HTTP layer)
                     │
                     ├─> services/uploading   validate → store file → DB record
                     ├─> services/extraction  pdfplumber → parser (pure) → draft
                     ├─> services/parser      pure functions text → fields (unit-tested here)
                     └─> db/repository        sqlite3, parameterized, transactions
```

**Upload → extract → review is one synchronous request.** Justification: files are
≤10 MB with a ≤5 s extraction target (NFR-3) and a single user — a background job
queue (threads/Celery/RQ) is complexity with no payoff today. Guard: a hard page
count cap (e.g. 50) bounds worst-case time; if a file exceeds it, reject with a
clear message (E-6).

Flow: `POST /upload` → validate (§12) → store file (UUID name) → insert row
(`uploaded`) → extract in-request → update row (`extracted` + draft JSON) →
redirect to `GET /invoices/<id>/review` → user corrects → `POST /invoices/<id>/save`
→ server-side validation → duplicate check (hash, vendor+number) → **single
transaction** writes final fields + lines (`saved`) → redirect to detail.
List/detail/edit/delete are conventional; delete removes DB row (cascade) **and**
stored file after confirmation (D-F).

---

## 11. Dependencies (Q10)

| Package | Why | Tier |
|---|---|---|
| Flask | Web framework; routing, forms, templating | Must |
| pdfplumber | PDF text/words/chars/tables (pulls pdfminer.six, Pillow) | Must |
| pytest | Test framework + Flask test client for integration tests | Dev |
| pypdfium2 | Rasterize PDF pages for OCR | Bonus only |
| pytesseract (+ Tesseract binary) | OCR | Bonus only |

Deliberately **excluded**: cloud SDKs (privacy), ORMs (thin repository is enough),
frontend frameworks/build tools (server-rendered), OCR in the Must tier (Tesseract
not installed on this machine). Versions pinned in `requirements.txt`; Sprint 0
verifies all wheels install cleanly on Python 3.14 (pure-Python pdfminer is safe;
Pillow/pypdfium2 ship 3.14 wheels — verified at install, not assumed).

---

## 12. Upload Security & Pre-Processing Validation (Q11, Q12)

Validation is an **ordered gate sequence** — reject early, say precisely why (US-7):

1. **Request size** — Flask `MAX_CONTENT_LENGTH` (e.g. 10 MB) rejects oversize before reading (AC-1.3).
2. **Presence** — file part exists, not 0 bytes (E-1).
3. **Extension whitelist** — `.pdf` (v1).
4. **Magic bytes** — content starts with `%PDF-` → catches executables/HTML renamed to `.pdf` (E-5). When the image tier exists: JPEG (`FF D8 FF`) / PNG signature.
5. **Openability** — pdfplumber opens it; ≥1 page; not encrypted (password-protected → specific message, E-3); page count ≤ cap (E-6).
6. **Store safely** — server-generated UUID filename, original kept as metadata only → path traversal impossible by construction (E-5, security §5); files under `uploads/`, never inside any code path.
7. **Record** — DB row (`uploaded`), SHA-256 hash computed for duplicate detection.

Serving stored files back: `send_from_directory` with the directory pinned to
`uploads/` (it refuses `../` escapes) and explicit mimetype `application/pdf` —
we only ever serve files we stored ourselves.

Security posture summary (from requirements §10, made concrete): bind `127.0.0.1`
only · Jinja autoescaping always on, extracted data never rendered raw (invoice
fields are third-party-controlled text — XSS) · parameterized SQL only · debug
mode acceptable *only because of* the localhost binding (documented coupling) ·
**cheap CSRF guard**: check `Origin`/`Host` header on POSTs — a malicious webpage
in the same browser *can* post forms at `127.0.0.1`, and this closes it for a few
lines (decision point) · no secrets anywhere (fully local).

## 13. Failure Handling (Q13)

Failure taxonomy with distinct handling:

| Class | Examples | Behavior |
|---|---|---|
| **Upload rejection** | wrong type, oversize, empty, magic mismatch, encrypted | Nothing stored; specific flash message naming problem + next step (AC-1.2–1.4) |
| **Extraction failure** | PDF opens but parser crashes; no text layer and OCR unavailable | Row kept, `status='failed'`, reason stored & shown; app unaffected (AC-2.5); retry = re-upload |
| **Partial extraction** ← the *common* case | some fields missing/ambiguous | `status='extracted'`; review form shows flags; user completes → save. **This is a normal flow, not an error** (AC-3.1) |
| **Save-time validation failure** | invalid date, non-numeric amount | Save blocked, per-field messages (AC-3.3) |

Principles: prefer `missing` over a wrong `found` (FR-6) · every failure is
visible in the list's status column (AC-7.2) · no input crashes the app (NFR-4) ·
the "no selectable text — likely a scan" message names the remedy (install
Tesseract / use a digital PDF).

## 14. Edge Cases (Q14)

The full 25-case catalogue lives in requirements §8; at the exploration level each
category maps to a owning mechanism:

| Category (E-refs) | Handled by |
|---|---|
| File-level rejects (E-1–E-6) | Upload gate sequence (§12) |
| No-text-layer / scans (E-4) | Text-length check after extraction → specific path (OCR tier or message) |
| Content ambiguity (E-10–E-16) | Parser strategy layers + preference orders + `ambiguous` status + consistency flags (§6) |
| Table quirks (E-15) | Row-level validation; drop-with-flag (§6 line items) |
| Duplicates / abandoned drafts (E-19–E-22) | Hash + vendor/number warning; server-side draft state (§7, §10) |
| Crash/interrupt (E-23) | Status lifecycle means every row is in a defined state; recovery = resume review |
| Operational (E-24–E-25) | Short-lived DB connections; dirs recreated on boot |

Newly identified during exploration (added to the test catalogue): PDFs with
damaged xref tables (pdfplumber may fail → extraction-failure path, not a crash) ·
fonts with broken Unicode maps (garbled text → fields come back `missing`, user
sees why) · rotated/landscape pages (verify pdfplumber handles; add a fixture).

## 15. Testing Strategy — what "done" means (Q15)

| Layer | Scope | Approach |
|---|---|---|
| **Parser unit tests** (largest share) | §6 strategies: each field rule against positive / negative / ambiguous / multi-candidate text; normalization (dates, amounts, currency); consistency checks | **Pure text fixtures** — no PDFs needed, since the parser takes text. Fast, exhaustive |
| **Validation unit tests** | Upload gates: magic bytes, size, extension, filename handling | Crafted fake files in tests |
| **Integration tests** | Flask test client + **temporary SQLite** (real data never touched): upload→review→save→list→detail→edit→delete; every failure mode renders a friendly page; atomicity (failed save rolls back; delete cascades + removes file); duplicate warning on same hash | Tiny **committed PDF fixtures** (2–3 hand-made small invoices) + generated corrupt/encrypted variants |
| **Smoke** | App boots, schema created, routes respond | pytest, run on every change |
| **Manual acceptance pass** | Against real invoices at the end; results recorded in the test-results doc | Scripted checklist = the Must ACs |

**Definition of complete:** all Must-tier acceptance criteria (US-1…US-7) pass —
automated where possible, documented manual pass where not; full suite green;
results logged. Should-tier (edit/delete/search/duplicates) per plan; Could-tier
only if time remains.

---

## 16. Recommended Technology Stack

| Layer | Choice |
|---|---|
| Language | **Python 3.14** (verified on this machine) |
| Web | **Flask** + Jinja2 templates (server-rendered) |
| Frontend | Hand-written CSS + minimal vanilla JS (no build step, offline-safe) |
| PDF | **pdfplumber** (text, words+coordinates, tables) |
| OCR (bonus tier) | pypdfium2 + pytesseract + Tesseract binary — only if gated checkpoint passes |
| Database | **SQLite** via built-in `sqlite3`, thin repository layer, no ORM |
| Testing | **pytest** (+ Flask test client) |

## 17. Recommended Architecture

Layered monolith, single process, localhost-only:

- **routes/** — thin HTTP layer (uploads, invoices blueprints); no business logic
- **services/** — `uploading` (gate sequence, storage, hashing), `extraction`
  (pdfplumber → parser → draft), `parser` (pure functions, no I/O)
- **db/** — schema (idempotent create), connection helper (short-lived, FKs on),
  repository functions
- **templates/ + static/** — server-rendered pages, local assets
- **data/invoices.db**, **uploads/** — created on boot, version-control-excluded

The two boundaries that buy testability and future options: the **parser is pure**
(text-in/draft-out) and the **extractor is behind one interface** (swap in OCR or
an LLM later without touching routes or storage).

## 18. Main Technical Components

1. Upload gate + safe file store (§12)
2. Extraction service: pdfplumber two-view text (plain + words+coords) (§3)
3. Field parser: label dictionaries → geometric lookup → pattern inference →
   validation → normalization → per-field status (§5–6)
4. Review form: server-side state, flags, validation (§10)
5. Repository + schema: invoices / invoice_lines, atomic save, cascading delete (§7)
6. Invoice management: list/search/sort, detail, edit, delete-with-confirmation
7. Failure & status surfacing: lifecycle + error messages (§13)

## 19. Risks & Mitigations (technical view)

| # | Risk | Mitigation |
|---|---|---|
| T-1 | Parser accuracy varies by layout (core risk, R-1) | Two-view extraction + preference-ordered strategies; `missing` over wrong; mandatory review; parser tuned on real samples; pure functions under heavy unit test |
| T-2 | Python 3.14 wheel availability | Sprint 0 installs and boots everything before building; pdfplumber is pure-Python at its core |
| T-3 | OneDrive sync vs SQLite locks (R-4) | Short-lived connections, small transactions; README: exclude folder from sync or pause during runs |
| T-4 | Tesseract absent → OCR tier likely slips | By design: OCR is gated; "no text layer" message ships regardless (AC-7.1) |
| T-5 | Vendor-name extraction unreliable (§5) | Always flagged; one-click manual entry in review — honest UX, not hidden weakness |
| T-6 | Synchronous extraction could exceed request patience on pathological files | Size + page-count caps; bounded worst case; reject with message (E-6) |
| T-7 | Drive-by cross-site POSTs to localhost | Origin/Host check on POSTs (few lines — decision point below) |

## 20. Technical Decisions Needing Approval

| # | Decision | Recommendation | Alternative |
|---|---|---|---|
| T-A | Overall approach | **A: Flask server-rendered + rules parser** (§1) | SPA, Node, LLM |
| T-B | Extraction engine | pdfplumber, two-view (text + words+coords), rules/labels | pypdf, PyMuPDF (AGPL) |
| T-C | v1 formats | PDF only; images+OCR as gated bonus tier | PDF+images now |
| T-D | Database access | `sqlite3` + thin repository, no ORM | SQLAlchemy |
| T-E | Money representation | `Decimal` at boundaries, `REAL` storage | INTEGER cents |
| T-F | Extraction timing | Synchronous in-request (≤5 s target) | Background queue |
| T-G | CSRF posture | Origin/Host check on POSTs (cheap) | Accept risk (localhost-only) |
| T-H | Concrete limits | 10 MB upload, 50 pages | Other limits |
| T-I | OCR tier | Only if core is green by mid-afternoon checkpoint | Skip entirely |
| T-J | Old `invoice-extractor/` folder | Move out of workspace before `git init` (nested repo = confusion) | Leave in place, ignore it |

---

## Approval

Awaiting approval of §16–§20. On approval, the next phase is **planning**:
project structure, data model finalization, sprint plan, and user-story mapping —
still no application code until the plan is approved.
