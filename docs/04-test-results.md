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
