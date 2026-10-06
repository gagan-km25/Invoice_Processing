# 12 — Project Retrospective

Sprint 6 deliverable · 2026-10-06 · **Evidence-based only** — every claim
below cites the issue log (docs/04), development log (docs/06), or prompt log
(docs/05). Six sprints, six commits, 169 tests, five real invoices verified.

---

## What went well

1. **The phase-gate process caught real problems before they cost time.**
   Sprint 5's planning audit found the no-text-layer gap (an AC-7.1
   requirement the implementation had silently missed) — it became a
   five-line fix plus tests instead of a surprise. The Sprint 2 "fresh start"
   discovery (an earlier prototype in the workspace) surfaced before anything
   was overwritten.
2. **Test-first discipline caught real defects, repeatedly.** The Sprint 2
   parser bring-up: a refactor NameError that blanked all extraction output
   was caught by the suite immediately (I-15); label-boundary bugs
   (`GSTIN` matching `gst`, `Subtotal` satisfying `total`) were found by
   tests before any wrong value could reach the database (I-9, I-11).
3. **The "prefer missing over guessed" principle held under pressure.** The
   parser returns per-field status and never silently guesses — which is why
   the currency glyph corruption (₹ extracting as `n`) became a *flagged
   inference* (INR, ambiguous, with recorded evidence) instead of silent
   wrong data (docs/07, finding 1).
4. **One commit per sprint, each gated on a green suite.** The history is a
   clean, explainable record: six commits, each mapping to a verified sprint
   (git log).
5. **Evidence-based decision-making worked.** The OCR gate was decided by
   re-inspecting the five real invoices (all text-based, zero images) rather
   than by opinion (docs/10 §5) — and the graceful "likely a scan" path ships
   regardless, so the decision is reversible.
6. **The issue log paid for itself.** I-1…I-31 made every failure and fix
   traceable, which is what made this retrospective writable without
   reconstruction.

## What went wrong

1. **The environment repeatedly interfered** (all logged): OneDrive
   re-synced `data/invoices.db` mid-acceptance, shifting ids and resurrecting
   "deleted" records (I-31 — risk T-3/R-4 materializing exactly as
   documented); the C: drive hit 100% mid-test-run (I-23); a OneDrive folder
   lock blocked the Sprint-0 archive move (I-1).
2. **Process-scripting mistakes produced false results.** `curl -X POST -L`
   re-sends POST on redirect, turning successful deletes into apparent 405s
   (I-30); `kill %1`/`$!` killed shell jobs instead of server processes,
   leaving orphan Flask servers double-bound to port 5000 with phantom 500
   responses (I-4); a test helper was referenced but never defined (I-22).
3. **Implementation bugs during parser bring-up** — seven in Sprint 2 alone
   (I-8…I-14): mid-line labels, GSTIN/gst label collision, rate-segment
   merging into amounts, Subtotal/total prefix collision, a tuple
   double-unpack producing zero line items, an eager vendor fallback inventing
   values, containment double-wrapping. All caught by tests before commit.

## Important debugging incidents (selected, full log in docs/04)

- **The phantom 500s (I-4).** Manual verification returned 500s that appeared
  in no server log. Diagnosis: three orphaned Flask servers from earlier
  background starts all bound port 5000 (Windows SO_REUSEADDR permits it) and
  one answered with an error page. Fix: kill by Windows PID from `netstat`;
  lesson recorded — never kill background servers by shell job id.
- **The tax amount that became 29,123,415.00 (I-9).** The label `gst`
  prefix-matched inside `GSTIN: 29AABCT1234F1Z5`, and the digits of the tax ID
  were parsed as an amount. Fix: word-boundary checks on both sides of every
  label match.
- **The vanishing line items (I-12).** The parse pipeline double-unpacked the
  (items, summaries) tuple, so the draft always showed zero lines even though
  extraction worked. Found by testing the component in isolation.
- **The OneDrive swap (I-31).** Mid-acceptance, invoice ids shifted and
  "deleted" records reappeared. Root cause: OneDrive re-synced the SQLite
  file between requests. Handled by re-running from a wiped database; the
  README now tells users to exclude the folder from sync or pause it.

## Lessons learned

1. **Verify environment assumptions — they fail more often than code.** Half
   the incident log is environment (OneDrive, port semantics, job control,
   locks), not application logic.
2. **State assertions beat response-body greps in end-to-end scripts.** After
   I-30, the acceptance scripts assert database state, not redirect bodies.
3. **"Not found" is a feature.** The never-guess principle made every parser
   bug a *test* failure instead of a *silent data corruption* failure.
4. **Small pinned dependency lists and zero system requirements are a
   reliability feature**, not just convenience (Sprint 5's OCR NO-GO preserved
   that).
5. **Phase gates with explicit approvals** kept six sprints of an ambiguous,
   exploration-heavy project coherent — each sprint started from an approved,
   citable document.

## What would be done differently

1. **Exclude the project folder from OneDrive from minute zero** (or move
   `data/` outside the synced tree) — it caused four of the incidents.
2. **Build the scripted acceptance harness in Sprint 1**, not Sprint 5 — the
   curl-based lifecycle checks would have caught the redirect/orphan-server
   confusions earlier.
3. **Write the PDF test factory before the upload sprint** — text-bearing
   fixture PDFs made Sprint 3's integration tests dramatically more valuable
   than blank-page fixtures.
4. **Capture background-process PIDs via the OS, not the shell**, from the
   first server launch.

## Current limitations (deliberate, documented)

- Edit-after-save is deferred (docs/09 §8); records are immutable once saved.
- History supports search only — no date-range filter or user-selected sort
  (FR-13 partial, deferred in Sprint 4).
- OCR is deferred (gate NO-GO); scanned PDFs are detected and rejected with a
  clear message rather than processed.
- CSV export was not selected.
- Vendor extraction is heuristic and always flagged for review (the letterhead
  has no label — an honest limitation of the domain).
- Single-user, localhost-only, DEBUG-mode development server by design.
- Accuracy is proven on five real layouts; unseen layouts may extract
  partially (by design the UI says so, field by field).

## What a production version would add

Edit-after-save; date-range filters and sort controls; an OCR tier behind the
existing extractor interface; packaging (installer or Docker); database
migrations tooling; background extraction with a job indicator; backup/
export; authentication if multi-user; structured logging; and a layout-test
corpus that grows with every unsupported invoice seen.
