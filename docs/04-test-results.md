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
