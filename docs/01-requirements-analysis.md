# 01 — Requirements Analysis

Project: **Invoice Extractor** — a local-only web application for uploading invoices,
automatically extracting their details, reviewing the result, and storing it in a
local database.
Date: 2026-10-06 · Status: **DRAFT — awaiting user approval**
Scope of this phase: analysis only. No architecture, no code, no sprint plan yet.

---

## 1. Project Objective & Problem Statement

**Problem.** Invoices arrive as files (PDF documents, scans). Turning them into
usable records means reading each file and retyping the vendor, invoice number,
dates, and amounts somewhere else. That is slow, boring, and error-prone, and the
structured data ends up disconnected from the source file.

**Objective.** Build a web application that runs entirely on the user's machine:

> Upload an invoice file → the app extracts the key fields automatically →
> the user reviews and corrects the result → the confirmed data is stored in a
> local database together with the original file.

**Design principle.** Extraction is assistive, not authoritative. The app does the
typing; the human confirms the truth. No extracted value is ever stored without
passing a review step.

**Success criteria for today.** The core flow (upload → extract → review → save →
browse) works end to end on typical digital PDF invoices, is covered by tests, and
is documented. Anything beyond that is a bonus tier (see priorities).

---

## 2. Main Users & Use Cases

Single user: the owner of the machine — someone who processes a moderate volume of
invoices (freelancer, small-business owner, or individual tracking expenses).
No roles, no accounts, no authentication. One persona is enough for a local tool.

| ID | Use case | Description |
|---|---|---|
| UC-1 | Process a digital invoice | Upload a text-layer PDF, check the extraction, correct if needed, save |
| UC-2 | Process a scanned invoice | Same flow for an image-only PDF or photo (stretch goal) |
| UC-3 | Look up a past invoice | Find a stored invoice by searching/browsing; view its details and original file |
| UC-4 | Fix or remove a record | Edit a stored invoice after the fact, or delete it entirely |
| UC-5 | Recover from a bad file | Get a clear, specific explanation when a file cannot be processed, and move on |

---

## 3. Functional Requirements

Priorities use MoSCoW (Must / Should / Could). "Must" = the app is not acceptable
without it today; "Should" = expected if the day goes normally; "Could" = bonus.

| ID | Requirement | Priority |
|---|---|---|
| FR-1 | Upload an invoice file via a browser page (file picker, drag-and-drop if cheap) | Must |
| FR-2 | Validate uploads before processing: extension **and** content check, size cap, corrupt/encrypted detection | Must |
| FR-3 | Store the original file on disk under a server-generated safe name and link it to its database record | Must |
| FR-4 | Extract text from the PDF text layer | Must |
| FR-5 | Parse the text into structured fields: vendor, invoice number, invoice date, due date, currency, subtotal, tax, total; line items where a recognizable table exists | Must |
| FR-6 | Show per-field extraction status (found / not found / ambiguous); never store or display a silently guessed value | Must |
| FR-7 | Provide a review screen where every extracted field is visible and editable, with validation before saving | Must |
| FR-8 | Save the invoice header and its line items to the local database in one atomic transaction | Must |
| FR-9 | List stored invoices (vendor, number, date, total, status), newest first | Must |
| FR-10 | Show a stored invoice's full detail and open the stored original file | Must |
| FR-11 | Show a specific, human-readable error for every failure mode; the app never crashes on bad input | Must |
| FR-12 | Edit a stored invoice's data | Should |
| FR-13 | Delete a stored invoice — database record **and** stored file — after confirmation | Should |
| FR-14 | Search (vendor, invoice number), filter (date range), and sort the list | Should |
| FR-15 | Warn on probable duplicates (same file hash, or same vendor + invoice number) but allow override | Should |
| FR-16 | Normalize dates and amounts on extraction; flag ambiguous values instead of guessing | Should |
| FR-17 | OCR fallback for scanned PDFs / image files (requires Tesseract) | Could — time-boxed |
| FR-18 | Export stored invoices to CSV | Could |

---

## 4. Non-Functional Requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-1 | Locality | 100% local execution: binds to `127.0.0.1` only, no cloud services, no external calls, works offline (no CDN assets) |
| NFR-2 | Privacy | Invoice files and data never leave the machine; data directories are excluded from version control |
| NFR-3 | Performance | Text-PDF extraction ≤ 5 s per file; page loads ≤ 1 s at local scale |
| NFR-4 | Reliability | No input crashes the app; every failure produces a readable message and leaves the system in a consistent state |
| NFR-5 | Data integrity | Header + line items save atomically; foreign-key constraints enforced; no orphan records |
| NFR-6 | Usability | Upload → review → save in a handful of clicks; plain-language errors that name the problem and the next step |
| NFR-7 | Maintainability | Layered structure (web / services / storage); extraction isolated behind one interface so it can be improved or replaced without touching the rest |
| NFR-8 | Testability | Parsers are pure, deterministic functions under unit test; tests run against a temporary database, never real data |
| NFR-9 | Portability | Fresh-Windows setup from the README: Python + one `pip install`; no required system dependencies (Tesseract optional, for OCR only) |
| NFR-10 | Capacity | Comfortable to ~10,000 invoices without redesign |

---

## 5. User Stories

**US-1 (Must) — Upload an invoice**
As a user, I want to upload an invoice file so the app can process it.

**US-2 (Must) — Extract the details automatically**
As a user, I want the app to pull the invoice fields out of the file so I don't retype them.

**US-3 (Must) — Review and correct before saving**
As a user, I want to check and fix the extracted values so wrong data never enters my records.

**US-4 (Must) — Save a confirmed invoice**
As a user, I want to save the reviewed invoice to the database so it is permanently stored.

**US-5 (Must) — See all stored invoices**
As a user, I want a list of saved invoices so I can find past ones.

**US-6 (Must) — See one invoice in full**
As a user, I want a detail view of a stored invoice, including its original file, so I can verify it.

**US-7 (Must) — Understandable failures**
As a user, I want a clear explanation when a file can't be processed so I know what to do next.

**US-8 (Should) — Edit a stored invoice**
As a user, I want to correct a saved invoice so records stay accurate over time.

**US-9 (Should) — Delete a stored invoice**
As a user, I want to remove a saved invoice and its file so my records stay clean.

**US-10 (Should) — Find invoices quickly**
As a user, I want to search, filter, and sort the list so I can locate an invoice fast.

**US-11 (Could) — Process scanned invoices**
As a user, I want scanned or photographed invoices to be extracted too, so I'm not limited to digital PDFs.

**US-12 (Could) — Export to CSV**
As a user, I want to export my invoices so I can use them in a spreadsheet.

---

## 6. Acceptance Criteria

### US-1 — Upload an invoice
- **AC-1.1** Given a valid text-layer PDF, when I upload it, then the file is accepted and stored, and I am taken to the extraction/review flow.
- **AC-1.2** Given a file with a disallowed type (e.g. `.txt`, `.exe`), when I upload it, then I see "Unsupported file type" and nothing is stored.
- **AC-1.3** Given a file over the size limit, when I upload it, then I see a size-limit message naming the limit.
- **AC-1.4** Given a 0-byte or corrupt file, when I upload it, then I see a "file could not be read" error and the app remains fully functional.

### US-2 — Extract the details automatically
- **AC-2.1** Given a text-layer PDF invoice, when extraction runs, then vendor, invoice number, invoice date, due date, currency, subtotal, tax, and total are populated where present in the document.
- **AC-2.2** Given a field that does not exist in the document, when extraction completes, then that field is shown as empty / "not found" — never a guessed value presented as found.
- **AC-2.3** Given a document with a recognizable line-item table, when extraction runs, then the line items are captured; given no recognizable table, then zero line items and no error.
- **AC-2.4** Given dates and amounts, when extracted, then they are normalized (ISO dates, decimal amounts, currency code); given an ambiguous value (e.g. `03/04/2025`), then it is flagged for review rather than silently interpreted.
- **AC-2.5** Given any extraction failure, then the upload is marked **failed** with the reason recorded, and the app does not crash.

### US-3 — Review and correct before saving
- **AC-3.1** Given extracted data, when the review page loads, then every field is visible and editable, and not-found or ambiguous fields are visually flagged.
- **AC-3.2** Given I correct a value and save, then the corrected value — not the original extraction — is what gets stored.
- **AC-3.3** Given an invalid value (bad date, non-numeric amount), when I try to save, then I get a validation message and the save is blocked.
- **AC-3.4** Given I leave the review page without saving, then the extracted draft is retained on the record so I can return to it without re-uploading.

### US-4 — Save a confirmed invoice
- **AC-4.1** Given a reviewed invoice, when I save, then the header and all line items are stored atomically and I see a success confirmation.
- **AC-4.2** Given the file hash or the vendor + invoice number matches an existing invoice, when I save, then I am warned about the probable duplicate and the save proceeds only after I confirm.
- **AC-4.3** Given a successful save, then the invoice appears in the list immediately.

### US-5 — See all stored invoices
- **AC-5.1** Given saved invoices exist, when I open the list, then each row shows vendor, invoice number, date, total, and status, newest first.
- **AC-5.2** Given no invoices exist, when I open the list, then I see an empty-state message with a link to upload.

### US-6 — See one invoice in full
- **AC-6.1** Given a stored invoice, when I open its detail page, then all header fields and all line items are displayed.
- **AC-6.2** Given a stored invoice, when I click "view original", then the stored source file opens in the browser.

### US-7 — Understandable failures
- **AC-7.1** Given each failure mode (unsupported type, oversize, corrupt file, encrypted PDF, PDF with no text layer, OCR unavailable), the error names the specific problem and, where possible, the next step.
- **AC-7.2** Given a failed processing attempt, a record of the failure with its reason is visible (retry possible), and the rest of the app works normally.

### US-8 — Edit a stored invoice
- **AC-8.1** Given a stored invoice, when I edit any field and save, then the change persists.
- **AC-8.2** Given an invalid value, when I save, then it is rejected with a validation message.

### US-9 — Delete a stored invoice
- **AC-9.1** Given a stored invoice, when I delete, then I am asked to confirm first.
- **AC-9.2** Given confirmation, then the database record (line items included) and the stored original file are removed, and the invoice disappears from all lists.

### US-10 — Find invoices quickly
- **AC-10.1** Given a search on vendor or invoice-number fragment, then only matching invoices are returned.
- **AC-10.2** Given a date-range filter or a sort by date/total, then results are correct.

### US-11 — Process scanned invoices (Could)
- **AC-11.1** Given an image-only PDF or image file, when extraction runs, then OCR is used, fields are populated, and the result is marked "extracted via OCR".
- **AC-11.2** Given Tesseract is not installed, then the user gets a clear message explaining that, and nothing crashes.

### US-12 — Export to CSV (Could)
- **AC-12.1** Given stored invoices, when I export, then a CSV is produced with one row per invoice and correctly escaped values that open cleanly in Excel.

---

## 7. Major Features

| # | Feature area | Covers |
|---|---|---|
| F1 | Upload & validation | FR-1, FR-2, FR-3 |
| F2 | Extraction engine | FR-4, FR-5, FR-6, FR-16 |
| F3 | Review & save | FR-7, FR-8, FR-15 |
| F4 | Invoice management | FR-9, FR-10, FR-12, FR-13, FR-14 |
| F5 | Reliability & feedback | FR-11 |
| F6 | OCR (stretch) | FR-17 |
| F7 | Export (stretch) | FR-18 |

F1–F5 form the minimum lovable product for today; F6–F7 are bonus tiers.

---

## 8. Edge Cases

**File-level**

| # | Case | Expected behavior |
|---|---|---|
| E-1 | 0-byte file | Rejected with "could not be read" |
| E-2 | Corrupt / truncated PDF | Rejected or marked failed with reason; no crash |
| E-3 | Password-protected / encrypted PDF | Specific "encrypted PDF" message |
| E-4 | PDF with no text layer (scan) | "No extractable text" — OCR if available, else clear message |
| E-5 | Executable or HTML renamed to `.pdf` | Content check catches mismatch; rejected |
| E-6 | Very large file / 200-page PDF | Size cap rejects; otherwise bounded processing time |
| E-7 | Multi-page invoice (line items span pages) | All pages parsed; line items aggregated |
| E-8 | Multiple invoices in one PDF | Out of scope v1 — first document processed; noted in message |
| E-9 | Non-invoice PDF (book chapter, bank statement) | Fields come back "not found"; user reviews/discards |

**Content-level**

| # | Case | Expected behavior |
|---|---|---|
| E-10 | Missing optional fields (no due date / tax / line items) | Shown as "not found"; save still allowed |
| E-11 | Multiple "total"-like candidates (subtotal, total, amount due, balance) | Parser preference order; ambiguous → flagged |
| E-12 | Ambiguous dates (`03/04/2025`, `4 Mar 2025`, `2025-03-04`) | Normalized when unambiguous; flagged when not |
| E-13 | Amount format variants (`1,234.56`, `1.234,56`, `$1,234.56`, `(123.45)`) | Normalization rules; unrecognized → flagged, not guessed |
| E-14 | Credit notes / negative totals | Parsed as negative; flagged |
| E-15 | Line-item table quirks (missing columns, merged rows, page-break splits) | Best effort; unparseable rows dropped with a review flag |
| E-16 | Subtotal + tax ≠ total | Save allowed (invoice is what it is), but flagged on review |
| E-17 | Unicode / special characters in vendor names | Stored and displayed correctly (UTF-8 end to end) |
| E-18 | Extremely long field values | Truncated/capped at a sane length with a flag |

**Workflow-level**

| # | Case | Expected behavior |
|---|---|---|
| E-19 | Same file uploaded twice | Duplicate warning (hash), override allowed |
| E-20 | Different file, same vendor + invoice number (corrected re-send) | Duplicate warning (vendor+number), override allowed |
| E-21 | Upload abandoned before saving | Record stays in `uploaded`/`extracted` state; resumable or discardable |
| E-22 | Browser refresh mid-review | Extracted draft still on the record (server-side state) |
| E-23 | Server stopped mid-extraction | Record remains in a defined state; app recovers on restart |
| E-24 | Database file locked (e.g. OneDrive sync) | Short-lived connections; readable error; documented workaround |
| E-25 | Uploads directory missing/deleted | Recreated on boot or reported clearly |

---

## 9. Technical Risks

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| R-1 | **Extraction accuracy varies by invoice layout** — the core risk of the product | Wrong data stored | Mandatory human review step by design; per-field found/not-found status; prefer "not found" over wrong; tune against real samples; extractor behind one interface so strategy can change |
| R-2 | Regex/label parsing is brittle and grows complex with each layout | Maintenance burden, regressions | Keep parsing pure and unit-testable; one normalization layer; keyword dictionaries; test per pattern; accept partial extraction |
| R-3 | Tesseract on Windows needs a manual install (OCR only) | Friction, possible skip | OCR is a time-boxed bonus tier; graceful degradation to a clear message |
| R-4 | Project folder is inside OneDrive sync; sync locking can corrupt SQLite or uploads | Data loss | Document prominently; recommend excluding the folder from sync or pausing during runs; keep DB connections short-lived |
| R-5 | Ambiguous date/amount formats silently corrupt data | Bad records | Normalization module + ambiguity flagging (FR-16, AC-2.4) |
| R-6 | **Scope creep vs. one-day deadline** | App unfinished at day's end | MoSCoW priorities; Must/Should/Could tiers; bonus features only after the core flow is green |
| R-7 | Dependency/install issues on the user's machine | Lost time | Minimal, pinned dependencies; README setup steps verified early (Sprint 0) |

---

## 10. Security & Data Privacy Considerations

Even for a local, single-user tool, these matter — and several are **correctness** issues that matter at any scale:

1. **Data locality (primary promise).** All files, data, and processing stay on the machine. No telemetry, no external requests at runtime, all assets served locally. Note: this rules out cloud-LLM extraction for v1 — sending invoices to an API would break the privacy story (see Decisions).
2. **Network exposure.** The server binds to `127.0.0.1` only — never `0.0.0.0` — so other devices on the network cannot reach it.
3. **No authentication — accepted risk, stated explicitly.** Fine because it is single-user localhost; anyone at the keyboard already has the files. Worth documenting rather than hiding.
4. **Upload validation.** Whitelist extensions *and* verify content (magic bytes: `%PDF-`, JPEG/PNG headers) so a renamed executable or HTML file (stored-XSS vector) is rejected. Enforce a size cap.
5. **Filename safety.** Never trust the user-supplied filename: generate server-side names (e.g. UUID) and store the original name only as metadata. This eliminates path traversal by construction.
6. **Serving stored files.** Contain file serving within the uploads directory (resolve and verify the resolved path stays inside it — no `../` escapes).
7. **XSS via invoice data.** Invoice fields are third-party-controlled text. Autoescaping stays on everywhere; extracted values are never rendered as raw HTML.
8. **SQL injection.** Parameterized queries only, no string-built SQL.
9. **Debug mode.** Development debug tooling is acceptable only because of the localhost-only binding (item 2); document this coupling so one is never changed without the other.
10. **Version-control hygiene.** Real invoices in `sample_invoices/`, plus `data/` and `uploads/`, must be git-ignored — if a remote is ever added, invoice data must not be pushed.
11. **No secrets.** A fully local design needs no API keys or credentials — a privacy benefit worth preserving when choosing the extraction approach.

---

## 11. Assumptions

1. Single user, at the same machine the app runs on; no concurrent access.
2. Invoices are primarily English, with US-style dates (`MM/DD/YYYY`) and amounts (`1,234.56`) as the default; normalization lives in one configurable module.
3. Digital (text-layer) PDFs are the primary input; scans/photos are a bonus tier for today.
4. Volume: hundreds to a few thousand invoices; files under ~10 MB.
5. A modern desktop browser (Chrome/Edge) on the same machine is the client.
6. Python is installed and the user can install packages into a virtual environment.
7. No backups, sync, multi-user, or deployment — the machine's own copies are the only copies.
8. "Complete today" means the Must tier tested and documented; Should tier if time allows; Could tier is bonus.

---

## 12. Decisions Needed Before Implementation

The fresh start reopens all technology decisions. Each needs an answer during the
exploration & planning phase; my recommendation is noted so they can be approved
as a set. **None are locked yet.**

| # | Decision | Options | Recommendation |
|---|---|---|---|
| D-A | **Technology stack** | Python+Flask+Jinja+SQLite+pytest · Node/Express · other | Python+Flask+SQLite: strongest PDF-parsing ecosystem; server-rendered pages fit upload→review→save; SQLite is zero-install |
| D-B | **Extraction approach** | Rules/regex on PDF text layer · local LLM (Ollama) · cloud LLM API · hybrid | Rules/regex: deterministic, testable, offline, no heavy downloads; keeps the locality promise; extractor pluggable for later upgrades |
| D-C | **Input formats for v1** | PDF only · PDF + JPG/PNG | PDF only. Images are useless without OCR, so bundling them means bundling OCR; add both together as the bonus tier |
| D-D | **Data scope** | Header fields only · header + line items | Header + line items (best effort) — line items carry the real value; built header-first so the core flow lands first |
| D-E | **Duplicate handling** | Warn + allow override · hard block | Warn + override: re-uploading a corrected scan is legitimate |
| D-F | **Delete semantics** | Remove DB record + stored file · DB record only | Remove both: "delete means delete"; confirmation dialog is the safety net |
| D-G | **OCR scope** | Attempt today (time-boxed) · defer entirely | Only if the core flow is complete and green by mid-afternoon |
| D-H | **Project location & old folder** | New project at workspace root (old `invoice-extractor/` moved out) · new subfolder alongside it | Move the old folder out of the tree before `git init` — a nested git repo inside the new project will cause confusion |
| D-I | **Locale defaults** | US conventions · other | US conventions as configurable default (assumption 2) |

---

## Approval

This analysis is **awaiting approval**. On approval, the next phase is exploration
& planning: technology spikes where needed, architecture, data model, and the
sprint plan — no application code before that phase is approved.
