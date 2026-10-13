"""Invoice processing pipeline: in-process queue + single serial worker.

Approved design (docs/ARCHITECTURE.md §4; P-E-05 job-ownership amendment):
- One `queue.Queue`, one worker thread — jobs execute serially, so two jobs
  for one invoice can never run concurrently within a boot.
- Queue entries are `(invoice_id, job_kind)`; kinds: `new_upload` (upload
  route), `reprocess` (reprocess endpoint), `recovery` (boot-time
  `recover_stalled()` only).
- **Job ownership:** only a `recovery` job may resume an invoice found in
  `processing` (or `extracted`, a crash-window state handled identically).
  Normal jobs encountering any non-`uploaded` state skip with a
  `job_skipped` event — they never auto-resume.
- **Enqueue dedupe:** a lock-guarded set of queued/running invoice ids;
  `enqueue` is a no-op for an id already present, whatever the kind. The id
  is released in the job's `finally`, so a later legitimate run
  (e.g. reprocess after completion) is not treated as a duplicate.
- **Retries:** a retryable failure is re-run inline up to
  `WORKER_MAX_ATTEMPTS` attempts **per processing episode** — each claim
  (upload, recovery resume, or reprocess) starts a fresh allowance.
  Exhaustion or a permanent failure performs exactly one terminal
  transition (`failed`) with the user-safe reason.
  `invoices.extract_attempts` accumulates lifetime attempts across episodes
  for observability only; it never shortens a later episode's allowance.
- **Error containment:** worker exceptions never kill the loop. Unexpected
  exceptions are re-raised as `PipelineError` (fixed template message,
  cause suppressed) whose sanitised traceback is the only thing
  `app.errors` ever sees; the events log carries the exception class name
  only.
- **Transient DB locks (M2):** SQLite lock/busy `OperationalError`s during
  claiming or pipeline persistence are retried with backoff, bounded by
  `WORKER_DB_MAX_ATTEMPTS` per job. A retry after a successful claim
  resumes the pipeline directly (the claim is transactional, so a lock
  error means it never committed); a partially-run pipeline is re-run
  idempotently. Non-lock database errors keep their existing containment.
  If lock retries are exhausted, the row keeps its current eligible status
  (`uploaded`/`processing`) and is picked up by boot-time recovery
  (`recover_stalled`) — never silently lost.

Tests drive the worker deterministically via `run_pending()` with
`WORKER_AUTOSTART=False` (conftest default).
"""
import sqlite3
import threading
import time
from queue import Empty, Queue

from flask import current_app

from app.db import get_db
from app.db.repository import (
    get_invoice,
    set_extract_attempts,
    transition_status,
)
from app.services import applog, extraction
from app.services.audit import (
    EVENT_EXTRACTION_COMPLETED,
    EVENT_EXTRACTION_FAILED,
    EVENT_INVOICE_UPLOADED,
    EVENT_PROCESSING_RESUMED,
)
from app.services.workflow import (
    ACTION_COMPLETE,
    ACTION_FAIL,
    ACTION_REPROCESS,
    ACTION_START,
    apply_transition,
)

JOB_NEW_UPLOAD = "new_upload"
JOB_REPROCESS = "reprocess"
JOB_RECOVERY = "recovery"

GENERIC_FAILURE_MESSAGE = (
    "Processing failed unexpectedly. You can try reprocessing this invoice."
)


class PipelineError(Exception):
    """Sanitised pipeline failure: fixed template message, cause suppressed
    at the raise site (`from None`), so its traceback — the only traceback
    `app.errors` may record — carries no exception text or invoice content."""


def _is_lock_error(exc: BaseException) -> bool:
    """True for transient SQLite lock/busy errors (the classic
    'database is locked' / 'database is busy' OperationalErrors). Message
    matching is the accepted approach — sqlite3 does not expose the
    extended error code on its exception objects. Anything else (e.g.
    'no such table') is NOT transient and must not be retried."""
    if not isinstance(exc, sqlite3.OperationalError):
        return False
    message = str(exc).lower()
    return "locked" in message or "busy" in message


class InvoiceWorker:
    """Single-worker job processor. One instance per app; tests use
    `run_pending()` instead of `start()`."""

    def __init__(self, app):
        self.app = app
        self._queue: Queue = Queue()
        self._active: set[int] = set()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------ queueing

    def enqueue(self, invoice_id: int, kind: str) -> bool:
        """Queue a job unless this invoice is already queued/running.
        Returns True when a job was actually enqueued."""
        with self._lock:
            if invoice_id in self._active:
                return False
            self._active.add(invoice_id)
        self._queue.put((invoice_id, kind))
        return True

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._loop, name="invoice-worker", daemon=True
        )
        self._thread.start()

    def _loop(self) -> None:
        while True:
            try:
                invoice_id, kind = self._queue.get()
            except Empty:  # pragma: no cover - get() blocks
                continue
            try:
                self.process_job(invoice_id, kind)
            except Exception as exc:  # pragma: no cover - containment
                # process_job contains its own failures; this is the last
                # resort so the loop can never die. Class name only.
                applog.log_event(
                    "worker_loop_error", error_class=type(exc).__name__
                )

    def run_pending(self) -> int:
        """Test/dev helper: run every currently queued job inline (serially,
        like the worker thread would). Returns the number of jobs run."""
        ran = 0
        while True:
            try:
                invoice_id, kind = self._queue.get_nowait()
            except Empty:
                break
            try:
                self.process_job(invoice_id, kind)
                ran += 1
            finally:
                self._release(invoice_id)
        return ran

    def _release(self, invoice_id: int) -> None:
        with self._lock:
            self._active.discard(invoice_id)

    def queued_count(self) -> int:
        return self._queue.qsize()

    # ------------------------------------------------------- recovery (boot)

    def recover_stalled(self) -> int:
        """Enqueue recovery jobs for invoices left in `uploaded` or
        `processing` (the approved eligible states — the extraction core
        never writes `extracted`, so no third crash state exists). Recovery
        itself writes nothing — the worker's claim ladder performs any
        transition."""
        with self.app.app_context():
            conn = get_db()
            try:
                rows = conn.execute(
                    "SELECT id FROM invoices "
                    "WHERE status IN ('uploaded', 'processing') ORDER BY id"
                ).fetchall()
            finally:
                conn.close()
        count = 0
        for row in rows:
            if self.enqueue(row["id"], JOB_RECOVERY):
                count += 1
        if count:
            applog.log_event("recovery_enqueued", count=count)
        return count

    # ------------------------------------------------------------ processing

    def process_job(self, invoice_id: int, kind: str) -> None:
        """Claim and run one job through the claim ladder, then the pipeline.
        Runs inside its own app context (the worker thread has none).

        Claim ladder (row status decides; see module docstring):
        - `uploaded`    → any kind claims it (T1: processing_started).
        - `processing`  → only `recovery` resumes (processing_resumed);
                          other kinds skip.
        - `failed` / `validation_failed` → only a `reprocess` job may claim
                          it (T5/T5b: → processing, audit reprocess_requested
                          in the same transaction); other kinds skip.
        - anything else → skip (stale job; e.g. terminal state reached).

        Transient SQLite lock errors are retried with backoff, bounded by
        `WORKER_DB_MAX_ATTEMPTS` per job (M2). On retry after a successful
        claim, the ladder is skipped (`claimed` flag) and the pipeline
        resumes directly — the claim transaction committed, so re-running it
        would be an illegal transition. On exhaustion the row keeps its
        current eligible status and is left for boot-time recovery
        (`recover_stalled`) — never silently lost.
        """
        try:
            max_db_attempts = self.app.config["WORKER_DB_MAX_ATTEMPTS"]
            backoff = self.app.config["WORKER_RETRY_BACKOFF_SECONDS"]
            claimed = False
            for db_attempt in range(1, max_db_attempts + 1):
                try:
                    with self.app.app_context():
                        conn = get_db()
                        try:
                            row = get_invoice(conn, invoice_id)
                            if row is None:
                                applog.log_event(
                                    "job_skipped", invoice_id=invoice_id,
                                    job_kind=kind, reason="missing",
                                )
                                return
                            status = row["status"]
                            if claimed:
                                # A previous attempt claimed this invoice and
                                # then hit a transient lock — resume the
                                # pipeline without re-running the ladder.
                                pass
                            elif status == "uploaded":
                                apply_transition(conn, invoice_id, ACTION_START)
                                claimed = True
                            elif status == "processing":
                                if kind != JOB_RECOVERY:
                                    applog.log_event(
                                        "job_skipped", invoice_id=invoice_id,
                                        job_kind=kind, reason="not_recovery",
                                    )
                                    return
                                from app.db.repository import insert_audit

                                insert_audit(
                                    conn, invoice_id, EVENT_PROCESSING_RESUMED,
                                    actor="system",
                                )
                                claimed = True
                            elif status in ("failed", "validation_failed"):
                                if kind != JOB_REPROCESS:
                                    applog.log_event(
                                        "job_skipped", invoice_id=invoice_id,
                                        job_kind=kind, reason=f"status_{status}",
                                    )
                                    return
                                apply_transition(conn, invoice_id, ACTION_REPROCESS)
                                claimed = True
                            else:
                                applog.log_event(
                                    "job_skipped", invoice_id=invoice_id,
                                    job_kind=kind, reason=f"status_{status}",
                                )
                                return
                        finally:
                            conn.close()

                        try:
                            self._run_pipeline(invoice_id)
                        except PipelineError as exc:
                            # Unexpected failure: sanitised traceback to app.errors
                            # only; generic user-facing message on the record.
                            applog.log_error(
                                f"pipeline failed for invoice {invoice_id}", exc_info=exc
                            )
                            self._fail_terminal(invoice_id, GENERIC_FAILURE_MESSAGE)
                    return
                except sqlite3.OperationalError as exc:
                    if not _is_lock_error(exc):
                        # Non-transient database error — keep the existing
                        # containment (loop-level logging; boot recovery
                        # remains the documented path for the row).
                        applog.log_event(
                            "worker_db_error", invoice_id=invoice_id,
                            error_class=type(exc).__name__,
                            reason="non_transient",
                        )
                        raise
                    if db_attempt >= max_db_attempts:
                        # Bounded lock retries exhausted: the row keeps its
                        # current eligible status (`uploaded`/`processing`)
                        # and is picked up by boot-time recovery — never
                        # silently lost, never forced to `failed`.
                        applog.log_event(
                            "worker_db_error", invoice_id=invoice_id,
                            reason="db_lock_exhausted", attempts=db_attempt,
                        )
                        return
                    applog.log_event(
                        "db_locked_retry", invoice_id=invoice_id,
                        attempts=db_attempt,
                    )
                    time.sleep(backoff)
        finally:
            self._release(invoice_id)

    # ------------------------------------------------------------- pipeline

    def _run_pipeline(self, invoice_id: int) -> None:
        # Retry allowance is PER PROCESSING EPISODE (review finding M1):
        # every claim — upload, recovery resume, or reprocess — starts a
        # fresh WORKER_MAX_ATTEMPTS allowance. The persisted counter
        # accumulates lifetime attempts for observability only and never
        # shortens a later episode's allowance.
        max_attempts = self.app.config["WORKER_MAX_ATTEMPTS"]
        backoff = self.app.config["WORKER_RETRY_BACKOFF_SECONDS"]

        conn = get_db()
        try:
            base_attempts = (
                get_invoice(conn, invoice_id)["extract_attempts"] or 0
            )
        finally:
            conn.close()

        attempt = 0
        while True:
            attempt += 1
            total = base_attempts + attempt  # lifetime count (observability)
            set_conn = get_db()
            try:
                set_extract_attempts(set_conn, invoice_id, total)
            finally:
                set_conn.close()

            try:
                ok, message = extraction.extract_stored_invoice(invoice_id)
            except extraction.ExtractionRetryable as exc:
                applog.log_event(
                    "extraction_retryable",
                    invoice_id=invoice_id,
                    attempts=total,
                )
                if attempt >= max_attempts:
                    self._fail_terminal(invoice_id, exc.user_message)
                    return
                time.sleep(backoff)
                continue
            except extraction.ExtractionPermanent as exc:
                applog.log_event(
                    "extraction_permanent",
                    invoice_id=invoice_id,
                    error_class=type(exc).__name__,
                )
                self._fail_terminal(
                    invoice_id,
                    exc.user_message,
                    raw_response=getattr(exc, "raw_response", None),
                )
                return
            except sqlite3.OperationalError:
                # Transient (lock) or non-transient DB error raised while
                # persisting the draft — the job-level handler in
                # process_job owns the lock-retry / containment decision.
                raise
            except Exception as exc:
                # Unexpected: sanitise at the boundary (P-E-05 amendment).
                applog.log_event(
                    "worker_error",
                    invoice_id=invoice_id,
                    error_class=type(exc).__name__,
                )
                raise PipelineError(
                    f"processing failed for invoice {invoice_id}"
                ) from None

            audit_conn = get_db()
            try:
                from app.db.repository import insert_audit

                insert_audit(
                    audit_conn,
                    invoice_id,
                    EVENT_EXTRACTION_COMPLETED,
                    actor="system",
                )
            finally:
                audit_conn.close()

            # T2: processing → completed (machine-validated; audit written in
            # the same transaction as the status change).
            complete_conn = get_db()
            try:
                apply_transition(complete_conn, invoice_id, ACTION_COMPLETE)
            finally:
                complete_conn.close()
            applog.log_event(
                "pipeline_completed",
                invoice_id=invoice_id,
                attempts=total,
            )
            return

    def _fail_terminal(
        self, invoice_id: int, user_message: str, raw_response: str | None = None
    ) -> None:
        """Exactly one terminal failure transition + audit events."""
        try:
            conn = get_db()
            try:
                row = get_invoice(conn, invoice_id)
                if row is None:
                    return
                if row["status"] == "failed":
                    return  # already terminal — never double-fail
                from app.db.repository import insert_audit

                insert_audit(
                    conn, invoice_id, EVENT_EXTRACTION_FAILED, actor="system"
                )
                transition_status(
                    conn,
                    invoice_id,
                    new_status="failed",
                    event_type="processing_failed",
                    actor="system",
                    details=None,
                    error_message=user_message,
                    raw_response=raw_response,
                )
            finally:
                conn.close()
            applog.log_event(
                "pipeline_failed", invoice_id=invoice_id, status="failed"
            )
        except Exception as exc:
            # Containment: failing to record a failure must not kill the loop.
            applog.log_event(
                "worker_error", invoice_id=invoice_id,
                error_class=type(exc).__name__,
            )


def record_upload_event(invoice_id: int) -> None:
    """Audit `invoice_uploaded` (called by the upload route after insert)."""
    conn = get_db()
    try:
        from app.db.repository import insert_audit

        insert_audit(conn, invoice_id, EVENT_INVOICE_UPLOADED, actor="vendor")
    finally:
        conn.close()
