# 04 — Test Results

Recorded test runs per sprint. The full case catalogue grows with each sprint
(categories defined in [03-plan.md](03-plan.md) §10). Every run below was
executed on this machine; tests never touch real data (temporary DB per
[tests/conftest.py](../tests/conftest.py)).

---

## Sprint 0 — Foundation · 2026-10-06

**Environment:** Windows 11 · Python 3.14.7 · Flask 3.1.3 · pdfplumber 0.11.10 · pytest 9.1.1

### Automated run — `venv\Scripts\python -m pytest -v`

```
============================= test session starts =============================
platform win32 -- Python 3.14.7, pytest-9.1.1, pluggy-1.6.0
configfile: pytest.ini
collected 3 items

tests/test_smoke.py::test_app_boots PASSED                               [ 33%]
tests/test_smoke.py::test_home_page_returns_200 PASSED                   [ 66%]
tests/test_smoke.py::test_schema_tables_exist PASSED                     [100%]

============================== 3 passed in 0.20s ==============================
```

**Result: 3 passed, 0 failed, 0 skipped.**

### Manual verification — real server boot

| Check | Expected | Observed |
|---|---|---|
| `venv\Scripts\python run.py` | server starts without error | ✅ `Running on http://127.0.0.1:5000` |
| Binding | localhost only (NFR-1) | ✅ `127.0.0.1` — not `0.0.0.0` |
| `GET /` via curl | HTTP 200 | ✅ 200 |
| Home page content | renders app shell | ✅ contains "Invoice Extractor" |
| `data/invoices.db` | created on boot with schema | ✅ created (idempotent DDL) |
| `uploads/` | created on boot | ✅ created |
| Server shutdown | clean Ctrl+C-equivalent kill | ✅ stopped |

### Dependency install (risk T-2 retirement)

All wheels installed cleanly on Python 3.14 — no build failures:
Flask 3.1.3, pdfplumber 0.11.10 (pdfminer.six 20260107, Pillow 12.3.0,
pypdfium2 5.14.0), pytest 9.1.1.

### Issues found during Sprint 0

| # | Issue | Resolution |
|---|---|---|
| I-1 | `mv` of the old project folder denied — a process held a directory handle (children were movable; folder itself was not) | Moved contents individually into `../invoice-extractor-archive-2026-10-05/`, verified git history intact (`f518ca8`), then removed the empty leftover folder. Nothing deleted; M-1 satisfied |
| I-2 | Wrong pip flag in first install command (`--disable-pip-version-warning`) | Retried with plain `pip install` — no project impact |
| I-3 | Git LF→CRLF warnings on Windows | Cosmetic (autocrlf); no action needed |

---

## Sprint 1 — Upload & Secure File Storage · 2026-10-06

**Environment:** Windows 11 · Python 3.14.7 · Flask 3.1.3 · pytest 9.1.1
**Suite result: 30 passed, 0 failed, 0 skipped** (17 unit + 10 integration + 3 smoke) in 3.45 s.

### Unit — upload gate sequence (`tests/unit/test_upload_gates.py`)

| ID | Scenario | Expected | Actual | Verdict |
|---|---|---|---|---|
| TC-S1-U01 | Valid PDF upload | Stored: file in `uploads/`, row `uploaded`, hash = SHA-256 of content, UUID stored name | As expected | ✅ Pass |
| TC-S1-U02 | Missing file part | Rejected `missing`, nothing stored | As expected | ✅ Pass |
| TC-S1-U03 | Empty filename (browser "no file chosen") | Rejected `missing` | As expected | ✅ Pass |
| TC-S1-U04 | 0-byte file (E-1) | Rejected `empty` | As expected | ✅ Pass |
| TC-S1-U05 | `.txt` extension | Rejected `extension` | As expected | ✅ Pass |
| TC-S1-U06 | `.PDF` uppercase extension | Accepted (case-insensitive) | As expected | ✅ Pass |
| TC-S1-U07 | Executable renamed `.pdf` (E-5) | Rejected `magic` | As expected | ✅ Pass |
| TC-S1-U08 | HTML renamed `.pdf` (XSS vector) | Rejected `magic` | As expected | ✅ Pass |
| TC-S1-U09 | Corrupt PDF, valid header (E-2) | Rejected `read_error` | As expected | ✅ Pass |
| TC-S1-U10 | Over size limit | Rejected `size` | As expected | ✅ Pass |
| TC-S1-U11 | Encrypted PDF (E-3) | Rejected `encrypted` | As expected (pdfplumber faked; gate logic under test) | ✅ Pass |
| TC-S1-U12 | 51-page PDF (E-6) | Rejected `pagecount` | As expected | ✅ Pass |
| TC-S1-U12b | Exactly 50 pages | Accepted, boundary safe | As expected | ✅ Pass |
| TC-S1-U13 | Traversal filename `../../evil.pdf` | Stored by UUID inside `uploads/`; nothing written outside; name kept as metadata only | As expected | ✅ Pass |
| TC-S1-U14 | Uploads dir deleted (E-25) | Recreated on demand; upload succeeds | As expected | ✅ Pass |
| TC-S1-U15 | Rejected upload stores nothing | No file, no DB row | As expected | ✅ Pass |
| TC-S1-U16 | Same bytes twice | Same `file_hash`, two rows; duplicate lookup finds original | As expected | ✅ Pass |

### Integration — upload flow over HTTP (`tests/integration/test_upload_flow.py`)

| ID | Scenario | Expected | Actual | Verdict |
|---|---|---|---|---|
| TC-S1-I01 | Full round trip | Redirect → success flash; file byte-identical; row listed on home page | As expected | ✅ Pass |
| TC-S1-I02 | POST with no file | "No file was selected"; nothing stored | As expected | ✅ Pass |
| TC-S1-I03 | `.txt` over HTTP | "Unsupported file type"; nothing stored | As expected | ✅ Pass |
| TC-S1-I04 | Corrupt PDF over HTTP | "could not be read"; nothing stored | As expected | ✅ Pass |
| TC-S1-I05 | Oversize body (Flask 413 backstop) | Friendly "File is too large" flash; nothing stored | As expected | ✅ Pass |
| TC-S1-I06 | 51 pages over HTTP | "exceeds the 50-page"; nothing stored | As expected | ✅ Pass |
| TC-S1-I07 | Traversal filename over HTTP | Stored safely by UUID inside `uploads/` | As expected | ✅ Pass |
| TC-S1-I08 | Duplicate upload (FR-15) | Non-blocking warning names prior record; both stored, same hash | As expected | ✅ Pass |
| TC-S1-I09 | Deleted uploads dir (E-25) | Recreated; upload succeeds | As expected | ✅ Pass |
| TC-S1-I10 | Localhost-only configuration | `HOST == "127.0.0.1"`, never `0.0.0.0`; 10 MB limit in config | As expected | ✅ Pass |

### Manual verification (real server + curl, `data/` + `uploads/`)

| ID | Check | Result |
|---|---|---|
| TC-S1-M01 | Valid PDF upload via HTTP | ✅ "Uploaded successfully (record #…)"; file stored; row created (`uploaded`, 1 page) |
| TC-S1-M02 | PDF-named file with non-PDF content | ✅ Rejected: "This file is not a valid PDF (its content does not match the PDF format)."; no row added |
| TC-S1-M03 | Duplicate upload warning | ✅ "…was uploaded before (record #2). It was stored again anyway." |
| TC-S1-M04 | Safe storage | ✅ Stored as `<uuid-hex>.pdf` inside `uploads/`, content begins `%PDF-`; client filename only in DB metadata |
| TC-S1-M05 | Localhost-only + clean shutdown | ✅ Bound to `127.0.0.1:5000` only; server stopped; no listeners remain |

Synthetic records created during manual verification were removed afterward — `uploads/` and the `invoices` table left empty.

### Issues found during Sprint 1

| # | Issue | Resolution |
|---|---|---|
| I-4 | Orphaned Flask processes from an earlier manual run double-bound port 5000 (Windows allows it), causing phantom HTTP 500s and confusion during verification | Killed by Windows PID from `netstat -ano`; lesson recorded: **stop background servers by listener PID, never by shell job id** |
| I-5 | Flash messages invisible to `curl -L` | Session cookie wasn't carried across the redirect; use `curl -c/-b` cookie jar (flashes are session-based by design) |
| I-6 | Test defects caught before green: missing fixture parameters (9 cases), tuple-vs-Row indexing in a helper, invalid bytes-f-string in the PDF factory | Fixed; suite then 30/30 |
| I-7 | First pip flag typo (`--disable-pip-version-warning`) | Retried with plain install; no impact |

### Coverage of required Sprint 1 scenarios (user checklist)

valid PDF → U01/I01/M01 · missing file → U02/I02 · non-PDF → U05/U08/I03/M02 · invalid/corrupt PDF → U09/I04 · >10 MB → U10/I05 · >50 pages → U12/I06 · unsafe filename/traversal → U13/I07 · duplicate → U16/I08/M03 · successful storage → U01/I01/M01/M04 · upload failure → U15/I02–I06 · upload dir handling → U14/I09 · localhost-only → I10/M05.

---

## Sprint 2 — Invoice Extraction & Parser · 2026-10-06

**Suite result: 88 passed, 0 failed, 0 skipped** in ~3 s (58 new cases; 3 smoke +
16 Sprint-1 gates + 10 Sprint-1 integration + 25 normalize + 14 field
strategies + 5 line-items + 7 robustness + 7 extraction/real-invoice).
Expected values for the five real invoices were transcribed from the Phase-A
exploration ([07-invoice-exploration.md](07-invoice-exploration.md)) **before**
parser implementation, and asserted exactly.

### Unit — normalization (`tests/unit/parser/test_normalize.py`)

| ID | Scenario | Verdict |
|---|---|---|
| TC-S2-N01 | Date `06-Oct-2026` → `2026-10-06` found | ✅ |
| TC-S2-N02 | ISO date → found | ✅ |
| TC-S2-N03 | `Mar 4, 2025` → found | ✅ |
| TC-S2-N04 | `4 Mar 2025` → found | ✅ |
| TC-S2-N05 | `03/04/2025` → US default + **ambiguous** flag | ✅ |
| TC-S2-N06 | `25/03/2025` → D/M proven → found | ✅ |
| TC-S2-N07 | `Due on receipt` → missing, never a date | ✅ |
| TC-S2-N08 | empty/None → missing | ✅ |
| TC-S2-N09 | `n1,250.00` (rupee glyph corruption) → 1250.00 | ✅ |
| TC-S2-N10 | `$1,234.56` → 1234.56 | ✅ |
| TC-S2-N11 | `1.234,56` European → 1234.56 | ✅ |
| TC-S2-N12 | `(123.45)` → −123.45 | ✅ |
| TC-S2-N13 | `n0.00` → 0.00 (zero is a value) | ✅ |
| TC-S2-N16 | bare `12` → 12.00 | ✅ |
| TC-S2-N15 | `n/a`, empty, None → None | ✅ |
| TC-S2-N17–N22 | currency resolution: symbol/code found, mojibake+GST → INR ambiguous, mojibake alone → ambiguous, none → missing; symbol detector ignores prose lines | ✅ |
| TC-S2-N23–N25 | invoice numbers incl. `GLF/26/4078`; prose never parses as number | ✅ |
| TC-S2-N27 | whitespace/NBSP collapse | ✅ |

### Unit — field strategies (`tests/unit/parser/test_fields.py`)

| ID | Scenario | Verdict |
|---|---|---|
| TC-S2-F01 | `Invoice No:` mid-line after vendor (finding 6) | ✅ |
| TC-S2-F02 | `Invoice Date: 06-Oct-2026` → ISO found | ✅ |
| TC-S2-F03 | real due date parses when present | ✅ |
| TC-S2-F04 | `Payment: Due on receipt` never becomes a due date | ✅ |
| TC-S2-F05 | bill-to multiline until item header | ✅ |
| TC-S2-F06 | vendor/address/tax-id from table cell | ✅ |
| TC-S2-F07 | `GST (18%) n1,179.00` → rate 18 + amount 1179 separately | ✅ |
| TC-S2-F11 | `GSTIN:` line never matches the `gst` amount label | ✅ |
| TC-S2-F08 | Grand Total preferred over Subtotal/Total | ✅ |
| TC-S2-F09 | `Subtotal` never satisfies generic `total` (prefix boundary) | ✅ |
| TC-S2-F10 | zero discount = found, not missing | ✅ |
| TC-S2-F12 | unrelated text → all 12 fields missing, nothing invented | ✅ |
| TC-S2-F13 | currency INR ambiguous with evidence kept | ✅ |
| TC-S2-F14 | geometric vendor fallback (no tables) — flagged ambiguous | ✅ |

### Unit — line items & robustness (`test_lines.py`, `test_robustness.py`)

| ID | Scenario | Verdict |
|---|---|---|
| TC-S2-L01 | items + summary rows separated cell-for-cell | ✅ |
| TC-S2-L02 | no table → zero lines, no error (AC-2.3) | ✅ |
| TC-S2-L03 | malformed rows dropped, not guessed (E-15) | ✅ |
| TC-S2-L04 | Quantity/Rate header variant recognized | ✅ |
| TC-S2-L05 | headerless totals-only table → zero items (totals via text layer) | ✅ |
| TC-S2-R01–R05 | empty/None/garbage/unicode/ragged-table input: all-missing draft, never a crash | ✅ |
| TC-S2-R06 | crashing strategy contained: its field missing + note, others parse | ✅ |
| TC-S2-R07 | meta (page count, parser version) recorded | ✅ |

### Integration — extraction flow + the five real invoices (`test_extraction_flow.py`)

| ID | Scenario | Verdict |
|---|---|---|
| TC-S2-I01 | upload → `extracted`: columns, draft JSON, flash, line table (synthetic text PDF over HTTP) | ✅ |
| TC-S2-I02 | vanished stored file → `failed` + readable `error_message` | ✅ |
| TC-S2-E01–E05 | the five real invoices, **exact expected values** for every header field, all line items cell-for-cell, currency INR (ambiguous), due-date missing, all consistency checks pass (skip if a sample is absent — samples are git-ignored) | ✅ |

### Field-level accuracy (final verification run, parser vs. exploration expected values)

| Invoice | Header/summary fields | Line items | Consistency checks |
|---|---|---|---|
| 001_retail | 13/13 | 3/3 | ✅ both |
| 002_services | 13/13 | 3/3 | ✅ both |
| 003_multiitem | 13/13 | 8/8 | ✅ both |
| 004_alternate | 13/13 | 4/4 | ✅ both |
| 005_complex | 13/13 | 5/5 | ✅ both |
| **Total** | **65/65 (100%)** — 5 of 65 are the currency field, correctly **flagged ambiguous** (INR inferred from GSTIN; glyph unmappable) | **23/23 (100%)** | 10/10 pass |

### Issues found and fixed during Sprint 2

| # | Issue | Fix |
|---|---|---|
| I-8 | Mid-line labels (`Vendor … Invoice No: X`) invisible to prefix matching | contains-based label match, longest-first, word boundaries both sides |
| I-9 | `GSTIN:` line matched the `gst` amount label → tax = 29,123,415.00 | suffix boundary check on labels |
| I-10 | `(18%)` rate segment merged into tax amount | rate segment stripped before amount parse |
| I-11 | `Subtotal` satisfied the generic `total` label → wrong total | prefix boundary check ('total' not inside 'Subtotal') |
| I-12 | parse() double-unpacked the line-items tuple → 0 lines | corrected unpacking |
| I-13 | Geometric vendor fallback invented vendors from garbage text | fallback gated on amount context + always flagged ambiguous |
| I-14 | Containment double-wrapped contained fields (found(missing(dict))) | `_as_field` coercion helper |
| I-15 | `tax_id` NameError after refactor → all fields missing (caught by suite) | use `fields["vendor_tax_id"]` |
| I-16 | Draft JSON serializes Decimals as strings | test expectation documents the JSON representation |
| I-17 | Sprint-1 round-trip expectations updated for extraction now running at upload (status `extracted`) | test updated, change documented |
