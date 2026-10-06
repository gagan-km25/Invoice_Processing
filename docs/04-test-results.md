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

---

## Sprint 3 — Review, Edit & Atomic Save · 2026-10-06

**Suite result: 128 passed, 0 failed, 0 skipped** in ~7 s (40 new cases; Sprint 0–2
regression all green). Design: [08-sprint3-design.md](08-sprint3-design.md).

### Unit — review validation service (`tests/unit/test_review_validation.py`)

| ID | Scenario | Verdict |
|---|---|---|
| TC-S3-U01 | Minimal valid form → ok, Decimals quantized | ✅ |
| TC-S3-U02 | Blank required fields (number/date/subtotal/total) → blocked | ✅ |
| TC-S3-U03 | `15/01/2026` → blocked, YYYY-MM-DD named | ✅ |
| TC-S3-U04 | Due date before invoice date → warning, not blocked | ✅ |
| TC-S3-U05 | `1250.5` → quantized `1250.50` | ✅ |
| TC-S3-U06 | Non-numeric subtotal → blocked, field named | ✅ |
| TC-S3-U07 | Currency: `usd`→USD, `euros` blocked, blank ok | ✅ |
| TC-S3-U08 | Quantity 0 → blocked ("above 0") | ✅ |
| TC-S3-U09 | Negative unit price → blocked | ✅ |
| TC-S3-U10 | Fully blank rows silently ignored (AC-03.4) | ✅ |
| TC-S3-U11 | Removed row dropped | ✅ |
| TC-S3-U12 | Numbers without description → error naming the row | ✅ |
| TC-S3-U13 | Line amount ≠ qty × unit → warning, save allowed | ✅ |
| TC-S3-U14 | subtotal+tax ≠ total → warning, save allowed (E-16) | ✅ |
| TC-S3-U15 | Kept lines renumbered 1..n in submitted order | ✅ |
| TC-S3-U16 | >200-char text rejected | ✅ |
| TC-S3-U17 | Empty form → the four required errors | ✅ |
| TC-S3-U18 | Draft prefill: values stringified, missing → blank, flags kept | ✅ |
| TC-S3-U19 | Blank-row slots continue index sequence | ✅ |
| TC-S3-U20 | parse_line_rows round-trips user input | ✅ |

### Integration — review → save over HTTP (`tests/integration/test_review_save_flow.py`)

| ID | Scenario | Verdict |
|---|---|---|
| TC-S3-I01 | Upload lands on review; values pre-filled; flags shown; Review link on home (AC-01.1/01.2) | ✅ |
| TC-S3-I02 | Unknown id → 404 (AC-01.4) | ✅ |
| TC-S3-I03 | Non-extracted record → friendly redirect, no form (AC-01.4) | ✅ |
| TC-S3-I04 | Corrected values persist exactly (AC-02.1) | ✅ |
| TC-S3-I05 | Untouched fields keep extraction values (AC-02.2) | ✅ |
| TC-S3-I06 | Line edit + remove + add on real invoice_001 (3 lines → 3 lines, renumbered) (AC-03.1–3) | ✅ |
| TC-S3-I07 | Blank add-rows store nothing (AC-03.4) | ✅ |
| TC-S3-I08 | Blocked validation persists nothing; errors rendered per field (AC-04.8) | ✅ |
| TC-S3-I09 | Totals mismatch → warning shown, save allowed (AC-04.7) | ✅ |
| TC-S3-I10 | `1080.5` stored quantized (AC-04.2) | ✅ |
| TC-S3-I11 | **Injected repository failure mid-transaction → full rollback** (header + lines unchanged) (AC-05.1) | ✅ |
| TC-S3-I12 | Double-submit of saved record rejected by status guard (AC-05.3) | ✅ |
| TC-S3-I13 | `extraction_json` byte-identical after save (AC-05.4) | ✅ |
| TC-S3-I14 | Duplicate vendor+number: warning, no record; confirm → saved (AC-06.1–3) | ✅ |
| TC-S3-I15 | Different file, same vendor+number → still flagged | ✅ |
| TC-S3-I16 | Different number → no duplicate warning | ✅ |
| TC-S3-I17 | Success flash + `saved` status (US-S3-07) | ✅ |
| TC-S3-I18 | Foreign Origin POST → 403; loopback Origin allowed (T-G) | ✅ |
| TC-S3-I19 | Duplicate finder: case-insensitive, saved records only | ✅ |
| TC-S3-I20 | Validation accepts real invoice_001 values without warnings | ✅ |

### Regression & real invoices

Sprint 0–2 suites: **all green** (smoke, upload gates, upload flow, parser,
extraction). The only prior-test edits: upload-flow tests now land on the
review page after the (changed) success redirect — assertions updated
transparently. Parser untouched this sprint; five real invoices re-verified:
**65/65 field checks, 23/23 line items, all five PASS.**

### Issues found and fixed during Sprint 3

| # | Issue | Fix |
|---|---|---|
| I-18 | Failed money validation left the raw string in the field → TypeError in consistency math | Set `None` on validation failure |
| I-19 | Warnings invisible when save succeeded without the duplicate detour | Warnings flashed on the success path too |
| I-20 | Origin check rejected `127.0.0.1` Origin when host was `localhost` | Loopback spellings treated as equivalent |
| I-21 | Rollback test: `sqlite3.Connection` is immutable; raw connection lacked `Row` factory | Injection moved to the repository `_to_real` boundary; Row factory set in test |
| I-22 | Test helper `_save` referenced but never defined | Added |
| I-23 | **Disk-full event (C: 100%)** during Phase D killed test runs | Cleaned own temp artifacts; verified with `-p no:cacheprovider`; flagged for user action (external cause — not project data) |

---

## Sprint 4 — History, Search, Details & Delete · 2026-10-06

**Suite result: 164 passed, 0 failed, 0 skipped** in ~20 s (36 new cases;
Sprint 0–3 regression all green). Design: [09-sprint4-design.md](09-sprint4-design.md).

### Unit — repository (`tests/unit/test_history_repository.py`)

| ID | Scenario | Verdict |
|---|---|---|
| TC-S4-U01 | list_saved returns only `saved` rows; drafts excluded | ✅ |
| TC-S4-U02 | Ordering: invoice_date desc, id desc tiebreak | ✅ |
| TC-S4-U03 | Number fragment search (`inv-00` → `INV-0042`) | ✅ |
| TC-S4-U04 | Vendor fragment search (`technova`) | ✅ |
| TC-S4-U05 | Case-insensitivity (covered by U03/U04 combined match) | ✅ |
| TC-S4-U06 | `%`/`_` treated as literals (escaped LIKE) | ✅ |
| TC-S4-U07 | No match → empty list | ✅ |
| TC-S4-U08 | count_saved consistent with list_saved, with/without q | ✅ |
| TC-S4-U09 | limit/offset paging windows correct (5 rows, page size 2) | ✅ |
| TC-S4-U10 | get_lines ordered by line_number | ✅ |
| TC-S4-U11 | delete removes row; lines cascade to zero; zero orphans | ✅ |
| TC-S4-U12 | delete guard: non-saved → ValueError, nothing changed | ✅ |
| TC-S4-U13 | Deleting one invoice leaves others + their lines intact | ✅ |

### Integration — history/detail/delete over HTTP (`tests/integration/test_history_delete_flow.py`)

| ID | Scenario | Verdict |
|---|---|---|
| TC-S4-I01 | History lists 3 saved invoices; a draft is excluded | ✅ |
| TC-S4-I01b | Exact ordering across three dates | ✅ |
| TC-S4-I02 | Summary columns render (number, vendor, date, total, status) | ✅ |
| TC-S4-I03 | Empty-history state with upload link (AC-01.3) | ✅ |
| TC-S4-I04 | Number search, case-insensitive (AC-03.1–3) | ✅ |
| TC-S4-I05 | Vendor search, case-insensitive | ✅ |
| TC-S4-I06 | No-match search state distinct from empty history (AC-03.5) | ✅ |
| TC-S4-I07 | `%` literal — wildcard would match everything, result is empty (AC-03.6) | ✅ |
| TC-S4-I07b | `_` literal — `A_B` does not match `ACX` | ✅ |
| TC-S4-I18 | `'; DROP TABLE invoices; --` inert; table intact (AC-R2) | ✅ |
| TC-S4-I21 | Page count shown ("page 1 of 1"); no paging links when unneeded | ✅ |
| TC-S4-I08 | Detail: complete header + View original (AC-04.1–3) | ✅ |
| TC-S4-I09 | Detail 404 unknown; non-saved → redirect (AC-04.4) | ✅ |
| TC-S4-I10 | History ↔ detail links (AC-04.5) | ✅ |
| TC-S4-I20 | Original serving: contained, `%PDF-` content | ✅ |
| TC-S4-I11 | Unconfirmed delete → confirmation page, nothing deleted (AC-05.2) | ✅ |
| TC-S4-I12 | Confirmed delete → success flash, gone from DB/history (AC-05.3) | ✅ |
| TC-S4-I13 | Cascade on real invoice (3 lines → 0); zero orphans (AC-06.1) | ✅ |
| TC-S4-I14 | Stored PDF removed; missing file tolerated with message (AC-06.2) | ✅ |
| TC-S4-I15 | Other invoices + lines untouched (AC-06.3) | ✅ |
| TC-S4-I16 | `GET /invoices/<id>/delete` → 405, nothing deleted (AC-05.4) | ✅ |
| TC-S4-I17 | Cross-site Origin delete → 403 (AC-05.5) | ✅ |
| TC-S4-I22 | Deleting an extracted (unsaved) draft refused (guard) | ✅ |
| TC-S4-I19 | Sprint 3 regression: upload → review → save flow intact (AC-R1) | ✅ |

### Regression & real invoices

Sprint 0–3 suites all green (128 prior + 36 new = 164). Parser untouched;
five real invoices re-verified after implementation: **65/65 field checks,
23/23 line items, all five PASS.**

### Issues found and fixed during Sprint 4

| # | Issue | Fix |
|---|---|---|
| I-24 | Missing `get_invoice` import in the repository test file | Added |
| I-25 | Cascade test deleted an **extracted** (not saved) record — guard correctly refused | Test now saves first, matching the approved guard |
| I-26 | `_upload_and_save` returns an id; regression test misused it as a response | Test rewritten against persisted state |
| I-27 | Test-file hygiene: stray placeholder constant, late import, contradictory assertion | Cleaned |

---

## Sprint 5 — Hardening, Edge Cases & OCR Gate · 2026-10-06

**Suite result: 169 passed, 0 failed, 0 skipped** (5 new cases; full Sprint
0–4 regression green). Design: [10-sprint5-design.md](10-sprint5-design.md).

### New tests (`tests/integration/test_sprint5_hardening.py`)

| ID | Scenario | Verdict |
|---|---|---|
| TC-S5-U01 | Valid PDF with no text → extraction fails with "likely a scan" message; record `failed` with reason (AC-01.1) | ✅ |
| TC-S5-U02 | Text-bearing PDFs unaffected by the gate (AC-01.3) | ✅ |
| TC-S5-I01 | HTTP: no-text PDF → flash + `failed` + review refused (AC-01.2) | ✅ |
| TC-S5-I03 | Error-path audit: wrong type, missing file, corrupt, oversize, unknown ids, GET-delete, injection search — **no 500s**, app healthy after (AC-02.1) | ✅ |
| TC-S5-I04/I05 | **Invoice data isolation**: two invoices; no value of A appears on B's review/detail/history and vice versa (AC-03.1–2) | ✅ |

### OCR Gate decision (US-S5-05) — **NO-GO / defer OCR**

Recorded evidence: all five real invoices are text-based (560–752 chars
extractable, zero images, stable tables — re-inspected this sprint);
pdfplumber extracts everything (65/65 fields, 23/23 lines across Sprints 2–5);
OCR is a gated **Could** tier (FR-17/T-I), not a requirement; Tesseract is not
installed; implementing OCR would add a system dependency and an entire
second extraction path for zero current invoices. The graceful "likely a
scan" failure (US-S5-01) ships instead, and the pluggable extractor keeps a
future OCR tier cheap. **No OCR code was added.**

### Manual acceptance — five real invoices, full lifecycle (US-S5-04)

Scripted HTTP run against the live server: upload → validate → extract →
review (prefilled) → save → history+search → detail → view original — then a
duplicate-delete cycle on a re-uploaded invoice.

| Invoice | upload+extract | review prefilled | save | history+search | detail | original |
|---|---|---|---|---|---|---|
| invoice_001_retail | ✅ | ✅ | ✅ saved | ✅ | ✅ | ✅ application/pdf |
| invoice_002_services | ✅ | ✅ | ✅ saved | ✅ | ✅ | ✅ |
| invoice_003_multiitem | ✅ | ✅ | ✅ saved | ✅ | ✅ | ✅ |
| invoice_004_alternate | ✅ | ✅ | ✅ saved | ✅ | ✅ | ✅ |
| invoice_005_complex | ✅ | ✅ | ✅ saved | ✅ | ✅ | ✅ |

Duplicate-delete cycle: upload warning ✅ · save-time 409 duplicate gate ✅ ·
confirmation checkbox ✅ · confirmed duplicate save ✅ · delete confirmation
step ✅ · confirmed delete + cascade ✅ · zero orphans ✅.

### Security regression (US-S5-06)

Origin/Host 403 on cross-site POSTs ✅ · GET-delete 405 ✅ · 404s ✅ ·
injection-safe search ✅ · contained original serving ✅ · invoice isolation ✅.

### Issues found and fixed during Sprint 5

| # | Issue | Fix |
|---|---|---|
| I-28 | No-text-layer PDFs silently became all-missing extractions (AC-7.1 gap) | No-text gate in the extraction service (US-S5-01) |
| I-29 | Duplicate banner listed the same record twice (vendor+number and hash both match) | Deduped id list in the save route |
| I-30 | Acceptance-script defects: `-X POST -L` re-sent POST on redirect (405 artifact), unquoted extra-args split, wrong grep targets for `&`-escaping and REAL rendering | Script fixed; **app unaffected** — all "failures" were script artifacts or the duplicate gate working |
| I-31 | **OneDrive re-synced `data/invoices.db` mid-acceptance** (ids shifted; saved records reappeared; "vanishing" rows) — risk T-3/R-4 materialized for real | Fresh re-run from a wiped DB passed cleanly; recommendation recorded: exclude this folder from OneDrive sync or pause it while the app runs |

---

## Sprint 6 — Final Verification, Documentation & Evaluation Readiness · 2026-10-06

**Suite result at HEAD `d22b855`: 169 passed, 0 failed, 0 skipped** —
re-verified twice (project venv **and** a pristine clean venv, TC-S6-S01).
No new feature tests were needed; Sprint 6 re-ran and consolidated existing
evidence, and added finalization records.

### Final verification records

| ID | Check | Result |
|---|---|---|
| TC-S6-R01 | Full regression at HEAD (project venv) | ✅ 169/0/0 |
| TC-S6-E01 | Five-invoice parser verification at HEAD | ✅ ALL 5 PASS — 65/65 fields, 23/23 lines |
| TC-S6-E02 | HTTP lifecycle at HEAD (all five invoices, every step) | ✅ ALL PASS (Sprint 5 acceptance steps re-run) |
| TC-S6-S01 | **NFR-9 clean-setup**: fresh venv → `pip install -r requirements.txt` → full suite → boot | ✅ install exit 0 · **169 passed with the clean venv** · boot HTTP 200 · venv removed afterwards |
| TC-S6-S02 | Security re-verification | ✅ all green in R01 (TC-S3-I18, TC-S4-I16/I17/I20, TC-S4-I18/I07, TC-S5-I04/I05) |
| TC-S6-E03 | No-text / scanned-PDF gate | ✅ TC-S5-U01/U02/I01 green in R01 |
| TC-S6-D01 | Docs links/terminology pass (docs 01–13) | ✅ FR-numbering erratum recorded (docs/09 §8 cited FR-14 for search; correct id is FR-13 — noted in docs/11) |
| TC-S6-D02 | README accuracy | ✅ A-1/A-2 fixed (Tesseract prerequisite → NO-GO note; docs table complete incl. 10–13); full review found no other stale claims |
| TC-S6-D03 | Traceability matrix complete | ✅ every FR/NFR classified — 24 PASS · 1 PARTIAL (FR-13) · 3 DEFERRED (FR-11, FR-17, FR-18) · 0 unexplained GAPs |
| TC-S6-D04 | Prompt/dev logs complete | ✅ P-01…P-14; dev log covers Sprints 0–6 chronologically with incidents |
| TC-S6-O01 | OCR gate recorded | ✅ NO-GO/deferred in docs/04, docs/10 §5, README |
| TC-S6-M01 | Reviewer walkthrough (docs only) | ✅ PASS — all 13 reconstruction points answerable from docs 01–13; no blocking gaps |

### Manual end-to-end acceptance re-run (live server)

The five real invoices were re-uploaded and driven through the complete
lifecycle at HEAD (upload → extract → review prefilled → save → history+search
→ detail → view original): **all steps PASS for all five invoices**, plus the
duplicate-delete cycle re-verified (upload warning, 409 duplicate gate,
confirmed duplicate save, delete confirmation, confirmed delete, cascade,
zero orphans). The application database was left populated with the five
saved invoices as a working demonstration state.

### Final Definition of Done — verified

**Functional:** all 13 pipeline behaviors evidenced (Sprint 1–5 suites +
Sprint 6 re-runs). **Quality:** 169/0/0 · security green · real invoices
65/65 · no raw exceptions on known paths · isolation proven · samples
unchanged (hashes match) · **clean-environment setup verified (TC-S6-S01)**.
**SDLC:** requirements/exploration/stories/ACs/architecture/sprint plans/
prompts/dev logs/tests/failures documented; Git history clean (6 sprint
commits); traceability matrix complete with honest GAP markings.
**Evaluation:** retrospective (docs/12) + Q&A (docs/13) + README/docs make
the project explainable without the developer (TC-S6-M01).
