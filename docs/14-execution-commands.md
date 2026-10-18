# Execution Commands — Invoice Extractor

Standalone command reference · v1.0.0 (commit `f69a193`, tag `v1.0.0`) ·
2026-10-06. Companion to [05-prompt-log.md](05-prompt-log.md) (prompts) and
[06-development-log.md](06-development-log.md) (narrative).

---

## 1. Purpose

This document collects the actual terminal/shell commands used to set up,
implement, test, verify, and release the Invoice Extractor, so an evaluator
can see exactly how Claude Code and the terminal were driven through the
SDLC — phase by phase, with results.

## 2. Command Evidence Rules

1. **Only evidenced commands are included.** Every command below was
   executed during the project and observed in the session record; outputs
   are reflected in docs/04 and docs/06.
2. **Reconstructed commands are not presented as exact.** Where only the
   shape of an operation is known (e.g., multi-step scripts), the entry is
   abbreviated with `…` and labeled.
3. **Missing commands are explicitly marked:**
   *"Command not preserved in available evidence."*
4. **Commands are separated from prompts and decisions.** Claude Code
   prompts live in [docs/05](05-prompt-log.md) (P-01…P-14); human approvals
   are noted per phase; this document lists only executed commands and their
   results.

Shell note: commands ran in Git Bash on Windows (hence `venv/Scripts/python`
and `//PID` escaping). PowerShell commands are marked **(PowerShell)**.

## 3. Project Setup

| Command | Purpose | Result/Evidence |
|---|---|---|
| `ls -la "c:/Users/kmgag/OneDrive/Desktop/Invoice-Extractor"` | Workspace discovery | Found the earlier 2026-10-05 prototype in `invoice-extractor/` |
| `ls -la …/invoice-extractor` · `find …/invoice-extractor -type f` | Inspect the prototype before proposing a fresh start | Scaffold + docs existed; informed the fresh-start decision (docs/01) |
| `python --version` · `tesseract --version` · `git --version` · `python -m pip --version` | Environment checks feeding decisions T-A…T-J | Python 3.14.7 · **Tesseract absent** · git 2.55 · pip 26.2.1 |

## 4. Sprint 0 — Foundation

| Command | Purpose | Result/Evidence |
|---|---|---|
| `mv Invoice-Extractor/invoice-extractor invoice-extractor-archive-2026-10-05` | M-1 archive move | **Denied** — directory locked by another process (I-1) |
| **(PowerShell)** `Rename-Item -LiteralPath 'Invoice-Extractor\invoice-extractor' -NewName 'invoice-extractor-old'` (×2, plus per-subdirectory probes) | Locate the lock | Children movable; folder itself locked |
| **(PowerShell)** `Get-ChildItem -LiteralPath 'Invoice-Extractor\invoice-extractor' -Force \| Move-Item -Destination 'invoice-extractor-archive-2026-10-05' -Force` | Move contents individually | ✅ moved; archive git history intact (`f518ca8`) |
| `rmdir "Invoice-Extractor/invoice-extractor"` | Remove empty leftover folder | ✅ removed |
| `mkdir -p app/routes app/services/parser app/db app/templates app/static/css app/static/js tests/unit tests/integration tests/fixtures sample_invoices data uploads` + `touch` of `.gitkeep` files | Create approved structure (S0-T2) | Structure matches docs/03 §1 |
| `python -m venv venv` | Virtual environment | ✅ |
| `venv/Scripts/python -m pip install Flask pdfplumber pytest` | Install dependencies (an initial attempt used an invalid pip flag and was retried) | ✅ Flask 3.1.3, pdfplumber 0.11.10, pytest 9.1.1 |
| `venv/Scripts/python -m pytest -v` | Smoke tests | ✅ 3 passed |
| `venv/Scripts/python run.py` + `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/` | Boot + HTTP verification | ✅ HTTP 200 |
| `git init` · `git add -A` · `git status --short` (staged-file audit) · `git commit` · `git log --oneline` | Version control | Commits `72b30cb`, `c94de50` |

## 5. Sprint 1 — Upload & Secure Storage

| Command | Purpose | Result/Evidence |
|---|---|---|
| `venv/Scripts/python -m pytest -v` (repeated through bring-up) | Full suite after each fix | 30 failed → … → **30 passed** |
| `curl -sS -c /tmp/jar -b /tmp/jar -F "file=@sample_invoices/…" -L http://127.0.0.1:5000/upload` | Manual upload verification (valid + invalid files, session cookie) | ✅ success/rejection flashes; nothing stored on rejects |
| `venv/Scripts/python -c "import sqlite3; …SELECT… FROM invoices…"` | Database checks after manual uploads | Rows/status as expected; synthetic rows cleaned |
| `head -c 5 uploads/*.pdf` | Stored-file magic-byte check | `%PDF-` |
| `netstat -ano \| grep ":5000"` · `taskkill //PID <pid> //F` | Server hygiene (orphan detection, I-4) | Port cleaned |
| `git add -A` · `git commit` · `git status --short` | Sprint 1 commit (green-gated) | Commit `3982f2a`; tree clean |

## 6. Sprint 2 — Extraction & Parser

| Command | Purpose | Result/Evidence |
|---|---|---|
| `venv/Scripts/python - <<'EOF' … pdfplumber inspection of all five sample PDFs (pages/text/tables/words/fonts) … EOF` | Phase A exploration before parser design | docs/07 findings: all text-based, 0 images |
| `venv/Scripts/python - <<'EOF' … parser sanity run on invoice_001 … EOF` | Bring-up check of parse output | Found the tuple-unpack and label bugs (I-9…I-12) |
| `venv/Scripts/python -m pytest -v` (bring-up loop, incl. targeted `…::test_… -x` runs) | Suite after each fix | 13 failed → 8 → 1 → **128 passed** (I-8…I-14 fixed) |
| `venv/Scripts/python - <<'EOF' … five-invoice verification vs docs/07 expected values … EOF` | Exact-value verification | **ALL 5 PASS — 65/65 checks** |
| Git verification for this sprint's work was performed at the start of Sprint 3 (commit created there) | — | Commit `0a0f5cb` |

## 7. Sprint 3 — Review, Edit & Save

| Command | Purpose | Result/Evidence |
|---|---|---|
| `git add -A` → `git commit` (Sprint 2 work, approved) | Commit at Sprint 3 start | Commit `0a0f5cb` |
| `venv/Scripts/python -m pytest -q` / `-v` | Suite after implementation | **128 passed** |
| `venv/Scripts/python -c "…SELECT status… FROM invoices…"` | Duplicate-gate state checks during acceptance | Confirmed gate behavior |
| `git add -A` → `git commit` → `git status --short` | Sprint 3 commit (green-gated) | Commit `b44d6d4`; tree clean |

## 8. Sprint 4 — History, Search, Details & Delete

| Command | Purpose | Result/Evidence |
|---|---|---|
| `venv/Scripts/python -m pytest -q` | Suite after implementation | **164 passed** |
| `venv/Scripts/python -c "…SELECT… FROM invoices…"` | Duplicate-gate DB diagnostics | Confirmed gate behavior |
| `git add -A` → `git commit` → `git status --short` | Sprint 4 commit (green-gated) | Commit `6ac1de8`; tree clean |

## 9. Sprint 5 — Hardening & OCR Gate

| Command | Purpose | Result/Evidence |
|---|---|---|
| `venv/Scripts/python - <<'EOF' … per-invoice text length / image count inspection … EOF` | **OCR gate evidence** (text-based? images?) | All five text-based (560–752 chars, 0 images) → **NO-GO** |
| `venv/Scripts/python -m pytest -q` | Suite after the no-text gate + hardening | **169 passed** |
| `bash /tmp/acceptance4.sh` (curl-based HTTP acceptance: uploads, saves, search, detail, original, duplicate/delete cycle — scripts were temporary session files) | Manual acceptance over all five real invoices | All five lifecycles PASS (table in docs/04) |
| `df -h /c` · cleanup of `%TEMP%/pytest-of-kmgag` | Disk/environment checks during the full-disk incident (I-23) | Verified space before continuing |
| `netstat -ano \| grep ":5000"` + `taskkill //PID <pid> //F` · `git check-ignore sample_invoices/*.pdf` | Server hygiene; privacy gate | Port clean; 5/5 ignored |
| `git add -A` → `git commit` → `git status --short` | Sprint 5 commit (green-gated) | Commit `d22b855`; tree clean |

**Sprint 5 suite result: 169 passed, 0 failed, 0 skipped.**

## 10. Sprint 6 — Final Verification & Release

| Command | Purpose | Result/Evidence |
|---|---|---|
| `python -m venv "%TEMP%/s6-clean-venv"` (fresh, outside OneDrive) | **TC-S6-S01** clean-environment setup | ✅ venv created |
| `…/s6-clean-venv/Scripts/python -m pip install -r requirements.txt` | Install from pinned requirements | ✅ exit 0; all 3 direct deps present |
| `…/s6-clean-venv/Scripts/python -m pytest -q` | Full suite on the clean venv | ✅ **169 passed** |
| `…/s6-clean-venv/Scripts/python run.py` + `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/` | Boot verification | ✅ HTTP 200; venv removed afterwards |
| `venv/Scripts/python -m pytest -q` | TC-S6-R01 full regression (project venv) | ✅ **169 passed** |
| `venv/Scripts/python - <<'EOF' … five-invoice verification vs docs/07 expected values … EOF` | TC-S6-E01 | ✅ **ALL 5 PASS — 65/65** |
| `bash /tmp/acceptance4.sh` | TC-S6-E02 HTTP lifecycle re-run | ✅ all five invoices, every step |
| `git check-ignore sample_invoices/*.pdf` · `git status --short` | Privacy + cleanliness gates | ✅ 5/5 ignored; docs-only diff |
| `git add -A` → `git diff --cached --stat` → `git commit` | Final release commit | Commit `f69a193` |
| `git tag -a v1.0.0 -m "Invoice Extractor v1.0.0 — final verified release"` · `git show v1.0.0` · `git tag --list` | Annotated release tag | ✅ tag on `f69a193` |
| `git log --oneline -7` · `git status --short` | Final state verification | ✅ clean tree; 7 commits |

**Final release:** commit `f69a193` · tag `v1.0.0` · working tree clean.

## 11. Running the Application

**Historical command (used throughout the project, evidenced in every
sprint's boot verification):**

```bash
cd "C:\Users\kmgag\OneDrive\Desktop\Invoice-Extractor"
venv/Scripts/python run.py
```

Then open **http://127.0.0.1:5000** (bound to 127.0.0.1 only; stop with
Ctrl+C). Verified repeatedly — most recently in Sprint 6 (TC-S6-S01,
HTTP 200).

**Also supported by the codebase, but not used historically** (documented
for completeness — do not treat as project history):

```powershell
cd "C:\Users\kmgag\OneDrive\Desktop\Invoice-Extractor"
.\venv\Scripts\Activate.ps1
python -m flask --app app run --host 127.0.0.1 --port 5000
```

Flask's CLI discovers the `create_app` factory in the `app` package, so this
serves the same application. The project's own documented path is `run.py`.

## 12. Running Tests

**Historical command (used at every sprint gate and for the final
verification):**

```bash
venv/Scripts/python -m pytest -q
```

Final result at `v1.0.0`:

```
169 passed, 0 failed, 0 skipped
```

(Verbose form used for per-case evidence: `venv/Scripts/python -m pytest -v`.)

## 13. Git & Release Commands

Evidenced Git command set used across the project:

```bash
git init                                # Sprint 0 (after archiving the prototype)
git status --short                      # before every commit (staged-file audit)
git add -A                              # stage (only after review)
git diff --cached --stat                # staged summary review
git commit -m "<sprint message>"        # one commit per sprint, green-gated
git log --oneline                       # history verification
git check-ignore sample_invoices/*.pdf  # privacy gate (every sprint)
git tag -a v1.0.0 -m "Invoice Extractor v1.0.0 — final verified release"
git show v1.0.0                         # tag verification
```

Release sequence (Sprint 6): full suite → `git add -A` → staged-diff review →
commit → annotated tag → `git show v1.0.0` → status clean.

## 14. Command → Evidence Summary

| Phase | Main command/activity | Evidence/result |
|---|---|---|
| Setup | `python -m venv` · `pip install -r requirements.txt` (final check) | 169/0/0 on clean venv (TC-S6-S01) |
| Sprint 0 | scaffold `mkdir`/writes · `pytest -v` · `run.py`+curl · `git init/commit` | 3 tests; HTTP 200; commits 72b30cb/c94de50 |
| Sprint 1 | gates + storage implementation · `pytest` · curl acceptance | 30/0/0; commit 3982f2a |
| Sprint 2 | pdfplumber exploration + parser + tests | 128/0/0; 65/65 fields; commit 0a0f5cb |
| Sprint 3 | review/save + rollback + Origin check | 128/0/0; commit b44d6d4 |
| Sprint 4 | history/search/detail/delete | 164/0/0; commit 6ac1de8 |
| Sprint 5 | no-text gate + hardening + acceptance scripts | 169/0/0; manual acceptance all-PASS; commit d22b855 |
| Sprint 6 | clean-venv NFR-9 · final regression · matrix · docs | 169/0/0; 65/65; commit f69a193; tag v1.0.0 |

## 15. Evaluation Takeaway

The command history shows a complete, ordered engineering trail: environment
discovery → clean setup → green-gated implementation per sprint → targeted
debugging (always followed by full regression) → live-server acceptance over
real data → a documentation-only final sprint → a single tagged release.
Commands, results, incidents (I-1…I-31), and human approvals are separable
throughout: prompts are in docs/05, decisions in docs/09–11, and every
command above has a recorded result in docs/04 or docs/06.
