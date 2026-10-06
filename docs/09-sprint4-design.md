# 09 — Sprint 4 Design: History, Search, Details & Delete

Phase: Sprint 4 planning (docs 01–08 approved; Sprint 3 complete at commit
`b44d6d4`, suite 128/0/0). Date: 2026-10-06.
Status: **DRAFT — awaiting user approval before implementation.**
Goal: extend the flow with **invoice history → search → details → delete**
for invoices that are already **saved**.

---

## 1. User Stories

| ID | Story | Tier |
|---|---|---|
| US-S4-01 | As a user, I want to view my saved invoices in an invoice history page. | Must |
| US-S4-02 | As a user, I want to see useful summary information for each saved invoice. | Must |
| US-S4-03 | As a user, I want to search saved invoices by invoice number or vendor. | Must |
| US-S4-04 | As a user, I want to open an invoice and view its complete saved details. | Must |
| US-S4-05 | As a user, I want to delete a saved invoice after confirmation. | Must |
| US-S4-06 | As a user, I want deleted invoice line items to be removed safely with the invoice. | Must |
| US-S4-07 | As a user, I want clear empty-state, success, and error messages. | Must |

One element beyond the seven stories, included because it was already
approved in requirements (FR-10) and the plan: the **detail page links to the
stored original file** ("view original") so the saved data can be verified
against the source. No other additions.

## 2. Acceptance Criteria

### US-S4-01 — History page
- **AC-01.1** `GET /invoices` lists only records with `status='saved'`;
  uploaded/extracted/failed drafts never appear.
- **AC-01.2** Newest first (ordered by invoice date desc, then id desc — the
  invoice's own date is the meaningful order for invoices; ties broken by id).
- **AC-01.3** With no saved invoices, a clear empty state with an upload link.

### US-S4-02 — Summary columns
Each history row shows: **invoice number, vendor, invoice date, total, and
status** (plus a Details link and a Delete control). (AC-02.1)

### US-S4-03 — Search
- **AC-03.1** A single search box matches against invoice number **or**
  vendor.
- **AC-03.2** Matching is case-insensitive ("technova" finds "TechNova").
- **AC-03.3** Partial fragments match ("inv-00" finds "INV-0042"; "nova"
  finds "TechNova").
- **AC-03.4** Search applies to saved records only, combined with AC-01.1/01.2.
- **AC-03.5** No matches → a "no invoices match your search" empty state that
  differs from the no-invoices-at-all state.
- **AC-03.6** User-supplied `%`/`_` are treated as **literal characters**,
  not wildcards (escaped in the LIKE pattern; injection-safe parameterization).

### US-S4-04 — Detail page
- **AC-04.1** `GET /invoices/<id>` shows the complete saved header: vendor,
  tax id, invoice number, invoice date, due date, bill-to, currency,
  subtotal, discount, tax rate, tax, total, status.
- **AC-04.2** All saved line items are listed with line number, description,
  quantity, unit price, amount.
- **AC-04.3** A "View original" link serves the stored source file.
- **AC-04.4** Unknown id → 404. Non-saved record → redirect with explanatory
  message (history/detail/delete operate on saved invoices only).
- **AC-04.5** History rows and the detail page link to each other.

### US-S4-05 — Delete with confirmation
- **AC-05.1** Delete is offered only from the detail page (and history row)
  and goes through a **confirmation step** before anything happens.
- **AC-05.2** A DELETE-intent request without confirmation renders the
  confirmation step and deletes **nothing**.
- **AC-05.3** After explicit confirmation, the record is deleted, the user
  sees "Invoice #N deleted.", and the invoice is gone from history.
- **AC-05.4** Deletion is **POST-only**; `GET /invoices/<id>/delete` must not
  delete (no delete route on GET → 405).
- **AC-05.5** Cross-site POSTs are rejected by the Sprint 3 Origin/Host check
  (403) — delete is covered by it like every POST.

### US-S4-06 — Safe line-item removal
- **AC-06.1** Deleting an invoice removes all of its `invoice_lines` rows
  (no orphans remain).
- **AC-06.2** The stored original file is deleted from `uploads/` as well
  ("delete means delete", FR-13/D-007); a missing file is tolerated with a
  warning rather than failing the deletion.
- **AC-06.3** Other invoices and their lines are untouched.

### US-S4-07 — Messages
- **AC-07.1** Empty history, empty search result, delete success, delete
  failure, and 404/non-saved redirects all produce clear, specific messages.

### Regression & safety
- **AC-R1** Sprint 0–3 suites stay green; the only prior-test edits are
  documented (upload success may link to the detail page — see §4).
- **AC-R2** All SQL remains parameterized; search terms are never
  string-interpolated.
- **AC-R3** Destructive operations require POST + confirmation + same-origin.

## 3. Exploration Findings (current state at `b44d6d4`)

| # | Question | Finding |
|---|---|---|
| 1 | Existing repository methods | `insert_invoice`, `get_invoice`, `find_by_hash`, `find_saved_duplicates`, `list_recent`, `update_extraction`, `save_invoice`. Nothing serves history search/paging, line fetching, or deletion. |
| 2 | New methods needed | `list_saved(q, limit, offset)`, `count_saved(q)`, `get_lines(invoice_id)`, `delete_invoice(invoice_id)`. Four small additions. |
| 3 | Schema sufficiency | **Fully sufficient.** History/detail/delete read exactly the columns that exist; the CHECK-constrained status column already distinguishes `saved`. |
| 4 | Schema changes necessary? | **No.** A vendor index was considered and rejected: the search is substring-`LIKE`, which indexes cannot serve; at NFR-10 scale (~10k rows) a filtered scan is fine. |
| 5 | `invoice_lines` deletion today | Two mechanisms exist: `ON DELETE CASCADE` (schema) and explicit `DELETE … WHERE invoice_id = ?` (used by `update_extraction`/`save_invoice` replace pattern). |
| 6 | CASCADE reliability | Reliable **when `PRAGMA foreign_keys = ON`** — `get_db()` sets it on every connection, which is the only supported path to the DB. Delete will still verify zero orphan rows in tests (trust but verify). |
| 7 | Saved-status filtering | `WHERE status = 'saved'` — same predicate as `find_saved_duplicates`; drafts stay visible only on the home recent panel, unchanged. |
| 8 | Search implementation | Parameterized `LIKE` with user wildcards escaped (`%`→`[%]`, `_`→`[_]`, and the escape char declared), wrapped in `… LIKE ? ESCAPE '\'`, case-insensitive (SQLite ASCII-case-insensitive LIKE; documented). One `q` searches `invoice_number` and `vendor`. |
| 9 | Pagination | **Necessary in a minimal form.** Unbounded rendering is wrong at NFR-10 scale (~10k). Chosen: `LIMIT 50 OFFSET (page-1)*50` + a `COUNT(*)` for "X invoices" + Older/Newer links. No page-number grids, no query-string gymnastics. |
| 10 | Route placement | Extend the existing `invoices` blueprint: `GET /invoices` (history), `GET /invoices/<id>` (detail), `POST /invoices/<id>/delete` (+ confirmation render). No new blueprint. |
| 11 | UI navigation | `base.html` header gains History / Upload links; home page recent-panel links to detail for `saved` rows; detail page links back to history and to the original file. |
| 12 | Layering | `routes/invoices.py` (HTTP) → **new `services/invoices.py`** (`delete_saved_invoice`: record lookup + repository delete + stored-file unlink + tolerant file-missing handling) → `repository` (SQL). Review/parser untouched. |

## 4. Design

**Routes**

```
GET  /invoices                     history: saved only, newest-first,
                                   ?q= search, ?page= paging (50/page)
GET  /invoices/<id>                detail: header + lines + view-original +
                                   delete control
GET  /invoices/<id>/original       serve stored file (contained in uploads/)
POST /invoices/<id>/delete         confirmed=0/absent → confirmation page
                                   confirmed=1 → delete + success flash → /invoices
```

- Upload success redirect **stays** on the home page (Sprint 3 tests assert
  it; with History + Review links nothing is unreachable). Documented
  non-change.
- Delete confirmation reuses the Sprint 3 pattern: first POST renders a
  confirmation page showing the invoice's key details + a confirm checkbox
  (state in the form, no server stash); confirmed POST performs the delete.

**Service layer.** `services/invoices.py`:
`delete_saved_invoice(invoice_id) -> (ok, message)` — loads the record
(404/guard at route), requires `status='saved'`, calls
`repository.delete_invoice`, then unlinks `uploads/<stored_filename>`
(missing file → warning text, deletion still succeeds). Returns user-facing
message halves like Sprint 3's extraction service.

**Repository methods** (all parameterized):
- `list_saved(conn, q=None, limit=50, offset=0)` — `WHERE status='saved'`
  [+ `AND (invoice_number LIKE ? ESCAPE '\' OR vendor LIKE ? ESCAPE '\')`]
  `ORDER BY invoice_date DESC, id DESC LIMIT ? OFFSET ?`
- `count_saved(conn, q=None)` — same WHERE, `COUNT(*)`
- `get_lines(conn, invoice_id)` — ordered by line_number
- `delete_invoice(conn, invoice_id)` — guard `status='saved'` →
  `DELETE FROM invoices WHERE id=?` (lines cascade) + COMMIT; returns nothing;
  orphan-check left to tests.

**Validation/security.** ids are ints (route converter); 404 + status guards;
search escaping as above; POST-only delete behind the existing global Origin
check; autoescaping everywhere; no new file-path handling beyond serving
`uploads/<stored_filename>` — which is server-generated, and served only via a
contained send (Sprint 3 serving pattern).

**Empty states / errors.** Three distinct states: no saved invoices at all;
no search matches; delete failure (e.g., DB error → flash + record intact).

## 5. Files to create / modify

| File | Change |
|---|---|
| `app/services/invoices.py` | **new** — delete orchestration (DB + file) |
| `app/templates/history.html` | **new** — history/search page |
| `app/templates/detail.html` | **new** — full detail + delete control |
| `app/templates/confirm_delete.html` | **new** — delete confirmation step |
| `app/db/repository.py` | `list_saved`, `count_saved`, `get_lines`, `delete_invoice` |
| `app/routes/invoices.py` | history/detail/original/delete routes |
| `app/templates/base.html` | header nav (History) |
| `app/templates/index.html` | saved rows link to detail |
| `app/static/css/style.css` | minor styles for detail/delete |
| `tests/unit/test_history_repository.py` | **new** — repository: filtering, search escaping, paging, delete/cascade |
| `tests/integration/test_history_delete_flow.py` | **new** — HTTP flows per §6 |
| `docs/04`, `docs/06`, `CHANGELOG.md`, `README.md` | sprint-end updates |

## 6. Test strategy (planned; not yet executed)

**Unit — repository (`tests/unit/test_history_repository.py`, real temp DB)**

| ID | Scenario | Expected |
|---|---|---|
| TC-S4-U01 | list_saved returns only saved rows | drafts excluded |
| TC-S4-U02 | ordering: invoice_date desc, id desc tiebreak | newest first |
| TC-S4-U03 | search by number fragment | only matches |
| TC-S4-U04 | search by vendor fragment | only matches |
| TC-S4-U05 | case-insensitive match | found |
| TC-S4-U06 | `%`/`_` in q treated literally | escaped pattern |
| TC-S4-U07 | no match → empty list | empty |
| TC-S4-U08 | count_saved matches list length, with and without q | consistent |
| TC-S4-U09 | limit/offset paging windows | correct slices |
| TC-S4-U10 | get_lines ordered by line_number | ordered |
| TC-S4-U11 | delete_invoice removes row; lines cascade to zero | no orphans |
| TC-S4-U12 | delete_invoice guard: non-saved → error, nothing changed | guarded |
| TC-S4-U13 | other invoices untouched by a delete | isolated |

**Integration — HTTP (`tests/integration/test_history_delete_flow.py`)**

| ID | Scenario | Expected |
|---|---|---|
| TC-S4-I01 | save 3 invoices → history lists 3, saved-only | AC-01.1 |
| TC-S4-I02 | summary columns render per row | AC-02.1 |
| TC-S4-I03 | empty history state | AC-01.3 |
| TC-S4-I04 | search box finds by number (case-insensitive fragment) | AC-03.1–3 |
| TC-S4-I05 | search by vendor fragment | AC-03.1–3 |
| TC-S4-I06 | no-match search state | AC-03.5 |
| TC-S4-I07 | `%` typed into search is literal | AC-03.6 |
| TC-S4-I08 | detail page: full header + lines + view original | AC-04.1–3 |
| TC-S4-I09 | detail unknown id → 404; non-saved → redirect | AC-04.4 |
| TC-S4-I10 | history ↔ detail links | AC-04.5 |
| TC-S4-I11 | delete without confirmation → confirmation page, nothing deleted | AC-05.2 |
| TC-S4-I12 | confirmed delete → gone from history, success flash | AC-05.3 |
| TC-S4-I13 | lines cascade-deleted, no orphans (AC-06.1) | verified in DB |
| TC-S4-I14 | stored file removed from uploads/ (AC-06.2); missing file tolerated | AC-06.2 |
| TC-S4-I15 | other invoices untouched (AC-06.3) | isolated |
| TC-S4-I16 | `GET /invoices/<id>/delete` → 405, nothing deleted (AC-05.4) | 405 |
| TC-S4-I17 | cross-site Origin delete POST → 403 (AC-05.5) | 403 |
| TC-S4-I18 | search term with SQL meta-characters (`'; DROP TABLE--`) → safe, literal | AC-R2 |
| TC-S4-I19 | regression: Sprint 3 review/save + upload flows unaffected | AC-R1 |
| TC-S4-I20 | view-original served with contained path (traversal attempt → 404) | security |

## 7. Risks & mitigations

| # | Risk | Mitigation |
|---|---|---|
| R-S4-1 | Accidental data loss via delete | Confirmation step + POST-only + Origin check + status guard; "delete means delete" is the documented, confirmed behavior (D-007) |
| R-S4-2 | LIKE wildcards/injection via search | Escaped patterns + parameterized SQL; dedicated injection test (TC-S4-I18) |
| R-S4-3 | Orphaned lines if CASCADE silently off | FK pragma on every connection (existing) + explicit zero-orphan assertions in tests |
| R-S4-4 | Stored-file unlink fails (locked/missing) | Tolerated: DB delete stands, warning surfaced; file removal is best-effort after the DB commit |
| R-S4-5 | Pagination over-engineering | Fixed page size, offset + count, Older/Newer links only |
| R-S4-6 | Scope creep (edit-after-save, export, bulk ops) | Hard exclusions below; conflict documented in §8 |

## 8. Scope exclusions & reported conflict

Excluded per instruction: authentication, OCR, cloud deployment, analytics,
AI features, **invoice editing after save**, bulk delete, export
(Excel/CSV/PDF), email, multi-user, unrelated UI redesign.

**⚠ Reported conflict (not silently resolved):** docs/03-plan.md's Sprint 4
row and requirements FR-11/US-8 (Should) include **editing a saved invoice**.
This sprint's instructions explicitly exclude edit-after-save. Resolution
follows the newer instruction: **edit-after-save is deferred to a later
sprint**; FR-11 stays on the requirements ledger as deferred-Should, and the
deferred status is recorded here and in the dev log. If Sprint 4 should
actually include it, say so before implementation.

## 9. Definition of Done (Sprint 4)

All ACs pass (automated); full suite green (Sprint 0–3 regression included);
docs/04 results recorded; logs + CHANGELOG + README updated; five real
invoices still verified and untouched; single commit after approval.

## 10. Implementation amendments (recorded post-implementation)

No architectural deviations. Two clarifications:
1. **History-row delete control** is a small per-row POST form targeting the
   same confirmation step (never a direct delete) — consistent with AC-05.1,
   which allows the delete control on "the detail page (and history row)".
2. **Original serving** is available for any existing record (not just
   saved) — review drafts may also need their source file; all security
   properties (contained serving, server-generated names) are unchanged.
