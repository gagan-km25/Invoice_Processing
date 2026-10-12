# ARCHITECTURE — Invoice Processing System Enhancement

Extends the v1 Invoice Extractor architecture (preserved in docs/02/03);
nothing is rebuilt. This document describes the *existing* baseline, the
*planned* enhancement, and what Sprint E0 has already put in place.

## 1. Existing baseline (v1, unchanged in E0)

Flask 3 app factory → thin blueprints (`routes/uploads.py`,
`routes/invoices.py`) → services (`uploading`, `extraction`, `review`,
`parser/`) → `db/repository.py` (all SQL). SQLite via short-lived
connections; `PRAGMA foreign_keys=ON` per connection; idempotent schema at
boot. Local-only UI (Jinja + local CSS/JS). Extraction: pdfplumber text
layer + rules/regex parser, synchronous in-request (replaced by the E1
pipeline).

## 2. Enhanced processing lifecycle (planned E1–E4)

```
Upload (PDF/JPG/PNG) ──gates──> record(status=uploaded) ──enqueue──> immediate response
                                                   │ (serial background worker)
                                                   ▼
                    processing → GLM extraction → response validation
                                                   ▼
                    business validation (§8) → duplicate classification (§9)
                                                   ▼
     completed ──review: correct & submit──> pending_approval ──> approved
         │                                        │
    validation_failed                     reject (reason required)
         │ (correct & resubmit)                   ▼
         └────────────────────────────────> rejected
     failed ◄── retries exhausted ── processing ──> reprocess
```

## 3. State model — four distinct dimensions (approved correction 2)

| Dimension | Storage | Values | Lifecycle effect |
|---|---|---|---|
| Processing status | `invoices.status` | uploaded, processing, completed, validation_failed, pending_approval, approved, rejected, failed | The only state machine (`workflow.TRANSITIONS`) |
| Validation verdict | `validation_status` + `validation_json` | passed / warning / failed | Drives T2/T3 and submit blocking; data, not a state |
| Duplicate classification | `dup_status` + `dup_matches` | none / possible / exact | Never changes status; warn-only, explained |
| Approval | status values + `approver_role`, `rejection_reason`, `acted_by`, `acted_at` | pending_approval / approved / rejected | Transitions T10/T11 only |

**Legal transitions** (enforced solely in `app/services/workflow.py`;
implemented in Sprint E0):

| ID | From | Action → To | Actor |
|---|---|---|---|
| T1 | uploaded | start → processing | worker dequeue (any job kind) |
| T2 | processing | complete → completed | pipeline (verdict passed/warning) |
| T3 | processing | validation_failed → validation_failed | pipeline (error findings) |
| T4 | processing | fail → failed | pipeline (extraction failure / malformed response after re-ask) |
| T5 | failed | reprocess → processing | vendor |
| T5b | validation_failed | reprocess → processing | vendor |
| T6 | validation_failed | submit → pending_approval | vendor (corrected data passes validation) |
| T7 | validation_failed | submit, still failing → stays | vendor |
| T8 | completed | submit → pending_approval | vendor |
| T9 | completed | submit with new errors → stays | vendor |
| T10 | pending_approval | approve → approved | approver with matching role |
| T11 | pending_approval | reject → rejected | approver with matching role; non-empty reason mandatory |

`approved` and `rejected` are terminal (Approved→Approved and
Approved→Rejected raise `InvalidTransition`). Corrections never trigger
re-extraction; Reprocess (T5/T5b) re-runs the pipeline.

## 4. Background processing & restart recovery (E1, approved design)

- One `ThreadPoolExecutor` with a single worker; `queue.Queue` entries are
  `(invoice_id, job_kind)` with kinds `new_upload`, `reprocess`, `recovery`.
- **Job ownership:** only a `recovery` job may resume an invoice found in
  `processing`; normal jobs encountering `processing` skip with a
  `job_skipped` log event. The claim ladder at dequeue:
  - `uploaded` → any kind CAS-claims it (T1, `processing_started` once).
  - `processing` → recovery resumes (audit `processing_resumed`, no second
    `processing_started`); other kinds skip.
  - other statuses → skip silently (stale job).
- **Concurrency:** one queue + one worker ⇒ serial execution; a
  lock-guarded in-memory set prevents duplicate enqueues of the same id
  within a boot; the claim ladder is the second guard.
- Boot-time `recover_stalled()` selects rows in `uploaded`/`processing` and
  enqueues `recovery` jobs; it writes **nothing** to the database itself.
- **Transient DB locks (Sprint E1, review M2):** SQLite lock/busy
  `OperationalError`s during claiming or persistence are retried with
  backoff, bounded by `WORKER_DB_MAX_ATTEMPTS` (default 3) per job. A retry
  after a successful claim resumes the pipeline directly — the claim is a
  single transaction, so no duplicate `processing_started` /
  `processing_resumed` is written; a partially-run pipeline is re-run
  idempotently. On exhaustion the row keeps its eligible status
  (`uploaded`/`processing`) and is picked up by boot-time recovery — never
  silently lost, never force-failed. Non-lock database errors keep the
  existing containment.
- Cross-boot: recovery is the sole resume path, once per boot. Two
  concurrent app instances on one DB are unsupported (single-user app).

## 5. Database design (Sprint E0 implemented)

- `invoices`: all v1 columns plus `file_type`, `po_number`,
  `bill_to_address`, `ship_to_name`, `ship_to_address`, `raw_response`,
  `validation_status/json`, `dup_status/matches`, `approver_role`,
  `rejection_reason`, `acted_by/at`, `extract_attempts`, `legacy_status`.
- `invoice_lines`: + `line_tax`.
- `invoice_audit`: id, invoice_id (FK cascade), event_type, actor, details,
  created_at; indexed per invoice.
- Status CHECK is **transitional**: 8 canonical states + deprecated v1
  values `extracted`/`saved` so pre-enhancement code keeps working until E5
  rewires review/save; a v3 tightening migration then removes them.
  Authoritative control is the workflow machine, which only accepts the 8.
- Migration v1→v2 (implemented, `app/db/migrations.py`): standard SQLite
  table rebuild in one transaction with FKs off, status mapping
  (extracted/saved → completed; original kept in `legacy_status`), one
  `record_migrated` audit row per invoice, `foreign_key_check` gate,
  `user_version` stamp. Live DB is never migrated before a recorded copy
  rehearsal (passed 2026-10-12) and a timestamped backup.

## 6. Roles and access map (planned E4; approved correction 4)

Session role labels — **not authentication**; any browser user can switch
roles; guards prevent wrong-role actions on a localhost single-user app.

| Route | vendor (default) | approver:manager / finance |
|---|---|---|
| `GET /` upload form | ✅ | ❌ hidden |
| `POST /upload` | ✅ | ❌ 403 |
| `GET /invoices` list, `GET /invoices/<id>` detail, `/status`, `/original` | ✅ | ✅ view-only |
| `GET /invoices/<id>/review` | ✅ | ❌ 403 |
| `POST .../save`, `/reprocess`, `/delete` | ✅ | ❌ 403 |
| `GET /approvals` | ❌ 403 | ✅ filtered to session role |
| `POST .../approve`, `/reject` | ❌ 403 | ✅ role must match `approver_role` |

Vendor visibility interpretation: the machine owner is the sole vendor, so
"view submitted invoices" = the invoice list. Actor values in audit are
session labels, not verified identities.

## 7. AI integration (planned E2; verified facts 2026-10-12)

- Endpoint `POST https://api.z.ai/api/paas/v4/chat/completions`,
  `Authorization: Bearer <key>`; OpenAI-SDK-compatible base URL.
- Text model `glm-4.6` (env-overridable) with native JSON mode
  (`response_format: {"type":"json_object"}`) for text-layer PDFs.
- Vision model `glm-4.5v` (env-overridable) for JPG/PNG and scanned PDFs
  (rasterised via pypdfium2, ≤3 pages, ≤5 MB/6000 px, base64). **Vision has
  no native JSON mode** → strict prompt + response validation + one re-ask.
- Fallback (decision 4): without a configured key, text PDFs use the
  existing local-rules parser; scans/images fail with a clear
  "AI extraction not configured" message.
- Key handling: environment only; never logged, committed, or returned.

## 8. Error handling & logging (planned E1; approved amendment)

- Two application loggers: `app.events` (structured allowlist via
  `log_event()`; cannot receive free-form payloads; never `exc_info`) and
  `app.errors` (the **only** traceback logger, fed exclusively
  boundary-sanitised domain exceptions built from fixed templates —
  original exceptions suppressed so no "Caused by" chain can carry
  sensitive text).
- User-facing errors are fixed generic strings; ids/counts only.
- `DEBUG=False` in normal boot from E1; global 500 handler renders a
  generic page and logs to `app.errors`.

## 9. Test strategy

See docs/TEST_PLAN.md. Tests always run on temporary databases; the GLM
client is stubbed in the suite — the network is touched only by the
recorded manual live smoke.
