"""Sprint E1 integration tests — asynchronous pipeline, retries, recovery,
job ownership, duplicate-job prevention, worker failures, audit, logging.

Test IDs per docs/TEST_PLAN.md §3. The worker runs in manual mode
(WORKER_AUTOSTART=False, backoff 0 via conftest): tests call
`worker.run_pending()` / `worker.process_job(...)` deterministically.
"""
import io
import sqlite3

import pytest
from werkzeug.datastructures import FileStorage

from app import create_app
from app.db import get_db
from app.db.repository import get_audit, get_invoice, insert_audit, insert_invoice
from app.services import applog, extraction, pipeline
from app.services.audit import (
    EVENT_EXTRACTION_COMPLETED,
    EVENT_EXTRACTION_FAILED,
    EVENT_INVOICE_UPLOADED,
    EVENT_PROCESSING_COMPLETED,
    EVENT_PROCESSING_FAILED,
    EVENT_PROCESSING_RESUMED,
    EVENT_PROCESSING_STARTED,
    EVENT_REPROCESS_REQUESTED,
)
from app.services.extraction import ExtractionRetryable
from app.services.pipeline import (
    GENERIC_FAILURE_MESSAGE,
    JOB_NEW_UPLOAD,
    JOB_RECOVERY,
)

SYNTHETIC_INVOICE = [
    "TAX INVOICE",
    "Acme Corporation Invoice No: INV-E1-0001",
    "1 Main Street, Springfield Invoice Date: 2026-01-15",
    "Subtotal $1,000.00",
    "Tax (8%) $80.00",
    "Grand Total $1,080.00",
]


def _rows(app, query="SELECT * FROM invoices ORDER BY id"):
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(query).fetchall()
    finally:
        conn.close()


def _upload(client, make_pdf, name, text_lines=SYNTHETIC_INVOICE):
    _, pdf_bytes = make_pdf(name, pages=1, text_lines=text_lines)
    return client.post(
        "/upload",
        data={"file": (io.BytesIO(pdf_bytes), name)},
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def _seed_processing_invoice(app, make_pdf, with_started_event=True):
    """Insert an invoice already in `processing` with a real stored file and
    (by default) a pre-existing processing_started audit row — a crashed run."""
    _, pdf_bytes = make_pdf("crashed.pdf", pages=1, text_lines=SYNTHETIC_INVOICE)
    stored_name = "uuid-crashed.pdf"
    (app.config["UPLOAD_DIR"] / stored_name).write_bytes(pdf_bytes)
    with app.app_context():
        invoice_id = insert_invoice(
            conn=get_db(),
            file_hash="hash-crashed",
            original_filename="crashed.pdf",
            stored_filename=stored_name,
            status="processing",
            page_count=1,
        )
        if with_started_event:
            insert_audit(
                get_db(), invoice_id, EVENT_PROCESSING_STARTED, actor="system"
            )
    return invoice_id


def _events(app, invoice_id):
    return [row["event_type"] for row in get_audit(_open_db(app), invoice_id)]


def _open_db(app):
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------- TC-ASYNC-01

def test_upload_returns_before_processing(app, client, worker, make_pdf):
    """TC-ASYNC-01 — upload responds without waiting for extraction; the
    record is still `uploaded` after the response and completes when the
    worker runs."""
    response = _upload(client, make_pdf, "async.pdf")
    assert response.status_code == 200
    assert b"Uploaded successfully" in response.data
    assert b"Processing continues in the background" in response.data

    row = _rows(app)[0]
    assert row["status"] == "uploaded"  # extraction has NOT run in-request
    assert worker.queued_count() == 1

    assert worker.run_pending() == 1
    row = _rows(app)[0]
    assert row["status"] == "completed"
    assert row["invoice_number"] == "INV-E1-0001"  # local extraction preserved
    assert row["extraction_json"]  # draft persisted for review
    assert row["extract_attempts"] == 1

    assert _events(app, row["id"]) == [
        EVENT_INVOICE_UPLOADED,
        EVENT_PROCESSING_STARTED,
        EVENT_EXTRACTION_COMPLETED,
        EVENT_PROCESSING_COMPLETED,
    ]


# ---------------------------------------------------------------- TC-ASYNC-02

def test_status_endpoint_tracks_progression(app, client, worker, make_pdf):
    """TC-ASYNC-02 — JSON status endpoint: uploaded → completed; 404 unknown."""
    response = _upload(client, make_pdf, "status.pdf")
    invoice_id = _rows(app)[0]["id"]

    payload = client.get(f"/invoices/{invoice_id}/status")
    assert payload.status_code == 200
    assert payload.get_json()["status"] == "uploaded"
    assert payload.get_json()["id"] == invoice_id

    worker.run_pending()
    payload = client.get(f"/invoices/{invoice_id}/status")
    assert payload.get_json()["status"] == "completed"

    assert client.get("/invoices/424242/status").status_code == 404


# ---------------------------------------------------------------- TC-SM-05

def test_upload_of_non_reviewable_record_guards(app, client, worker, make_pdf):
    """TC-SM-05 — a completed (pipeline output) invoice is reviewable; an
    uploaded (not yet processed) one is not."""
    _upload(client, make_pdf, "rev.pdf")
    invoice_id = _rows(app)[0]["id"]

    blocked = client.get(f"/invoices/{invoice_id}/review", follow_redirects=True)
    assert b"only extracted or completed invoices can be reviewed" in blocked.data

    worker.run_pending()
    ok = client.get(f"/invoices/{invoice_id}/review")
    assert ok.status_code == 200


# ---------------------------------------------------------- TC-PIPE-FAIL-01

def test_permanent_failure_scan_gate(app, client, worker, make_pdf):
    """TC-PIPE-FAIL-01 — no-text PDF: permanent failure, terminal `failed`
    with the user-safe scan reason, exact audit sequence."""
    _upload(client, make_pdf, "blank.pdf", text_lines=None)
    invoice_id = _rows(app)[0]["id"]

    worker.run_pending()
    row = _rows(app)[0]
    assert row["status"] == "failed"
    assert "likely a scan" in row["error_message"]
    assert row["extract_attempts"] == 1  # permanent: never retried
    assert _events(app, invoice_id) == [
        EVENT_INVOICE_UPLOADED,
        EVENT_PROCESSING_STARTED,
        EVENT_EXTRACTION_FAILED,
        EVENT_PROCESSING_FAILED,
    ]


# ---------------------------------------------------------- TC-PIPE-FAIL-02

def test_retryable_failure_then_success(app, client, worker, make_pdf, monkeypatch):
    """TC-PIPE-FAIL-02 — a transient failure is retried and completes;
    the attempt counter is persisted."""
    _, pdf_bytes = make_pdf("flaky.pdf", pages=1, text_lines=SYNTHETIC_INVOICE)
    response = client.post(
        "/upload",
        data={"file": (io.BytesIO(pdf_bytes), "flaky.pdf")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert response.status_code == 200
    invoice_id = _rows(app)[0]["id"]

    calls = {"n": 0}
    real_extract = extraction.extract_stored_invoice

    def flaky(invoice_id):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ExtractionRetryable("The stored file could not be read right now.")
        return real_extract(invoice_id)

    monkeypatch.setattr(extraction, "extract_stored_invoice", flaky)
    worker.run_pending()

    row = _rows(app)[0]
    assert row["status"] == "completed"
    assert row["extract_attempts"] == 2  # one retryable failure + one success
    assert calls["n"] == 2
    assert _events(app, invoice_id) == [
        EVENT_INVOICE_UPLOADED,
        EVENT_PROCESSING_STARTED,
        EVENT_EXTRACTION_COMPLETED,
        EVENT_PROCESSING_COMPLETED,
    ]  # extraction_failed NOT recorded — the run ultimately succeeded


# ---------------------------------------------------------- TC-PIPE-FAIL-03

def test_retry_exhaustion_terminal_failure(app, client, worker, make_pdf, monkeypatch):
    """TC-PIPE-FAIL-03 — persistent retryable failure exhausts the bound and
    terminates exactly once (no per-retry audit spam)."""
    _, pdf_bytes = make_pdf("gone.pdf", pages=1, text_lines=SYNTHETIC_INVOICE)
    client.post(
        "/upload",
        data={"file": (io.BytesIO(pdf_bytes), "gone.pdf")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    invoice_id = _rows(app)[0]["id"]
    (app.config["UPLOAD_DIR"] / _rows(app)[0]["stored_filename"]).unlink()

    def always_retryable(invoice_id):
        raise ExtractionRetryable("The stored file could not be read right now.")

    monkeypatch.setattr(extraction, "extract_stored_invoice", always_retryable)
    worker.run_pending()

    row = _rows(app)[0]
    assert row["status"] == "failed"
    assert row["extract_attempts"] == app.config["WORKER_MAX_ATTEMPTS"]
    assert "could not be read" in row["error_message"]
    assert _events(app, invoice_id) == [
        EVENT_INVOICE_UPLOADED,
        EVENT_PROCESSING_STARTED,
        EVENT_EXTRACTION_FAILED,
        EVENT_PROCESSING_FAILED,
    ]  # exactly one terminal pair despite 3 attempts


# ---------------------------------------------------------- TC-PIPE-FAIL-04

def test_worker_error_contained_and_sanitised(app, client, worker, make_pdf, monkeypatch):
    """TC-PIPE-FAIL-05 — an unexpected exception becomes a generic terminal
    failure; the exception text never reaches the record, responses, or logs
    (sanitised-boundary rule)."""
    _, pdf_bytes = make_pdf("boom.pdf", pages=1, text_lines=SYNTHETIC_INVOICE)
    client.post(
        "/upload",
        data={"file": (io.BytesIO(pdf_bytes), "boom.pdf")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    invoice_id = _rows(app)[0]["id"]

    def exploding(invoice_id):
        raise RuntimeError("SECRET-EXCEPTION-SENTINEL details")

    monkeypatch.setattr(extraction, "extract_stored_invoice", exploding)
    worker.run_pending()

    row = _rows(app)[0]
    assert row["status"] == "failed"
    assert row["error_message"] == GENERIC_FAILURE_MESSAGE
    assert "SECRET-EXCEPTION-SENTINEL" not in row["error_message"]

    events = applog.events_log_path(app).read_text(encoding="utf-8")
    errors = applog.errors_log_path(app).read_text(encoding="utf-8")
    assert "error_class=RuntimeError" in events
    assert "SECRET-EXCEPTION-SENTINEL" not in events
    assert "pipeline failed for invoice" in errors
    assert "SECRET-EXCEPTION-SENTINEL" not in errors


# ---------------------------------------------------------- TC-PIPE-FAIL-06

def test_reprocess_after_failure(app, client, worker, make_pdf, monkeypatch):
    """TC-PIPE-FAIL-06 — failed invoice: reprocess audits the request and
    completes when the transient condition clears; illegal reprocess is
    refused without enqueueing."""
    _, pdf_bytes = make_pdf("vanish.pdf", pages=1, text_lines=SYNTHETIC_INVOICE)
    client.post(
        "/upload",
        data={"file": (io.BytesIO(pdf_bytes), "vanish.pdf")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    invoice_id = _rows(app)[0]["id"]
    stored = app.config["UPLOAD_DIR"] / _rows(app)[0]["stored_filename"]
    stored.unlink()  # transient unreadable file
    worker.run_pending()
    assert _rows(app)[0]["status"] == "failed"

    # unknown invoice id → 404, never a job
    assert client.post("/invoices/424242/reprocess").status_code == 404

    stored.write_bytes(pdf_bytes)  # transient condition clears
    response = client.post(f"/invoices/{invoice_id}/reprocess", follow_redirects=True)
    assert b"Reprocessing record" in response.data
    assert _rows(app)[0]["status"] == "failed"  # nothing happens until the worker runs

    worker.run_pending()
    row = _rows(app)[0]
    assert row["status"] == "completed"
    # attempts accumulate across episodes for observability (M1):
    # 3 from the exhausted first episode + 1 successful reprocess attempt.
    assert row["extract_attempts"] == app.config["WORKER_MAX_ATTEMPTS"] + 1
    events = _events(app, invoice_id)
    assert events.count(EVENT_REPROCESS_REQUESTED) == 1  # audited with T5
    assert events[-3:] == [
        EVENT_REPROCESS_REQUESTED,
        EVENT_EXTRACTION_COMPLETED,
        EVENT_PROCESSING_COMPLETED,
    ]

    # now illegal: completed invoices cannot be reprocessed
    before_events = _events(app, invoice_id)
    refused = client.post(f"/invoices/{invoice_id}/reprocess", follow_redirects=True)
    assert b"only failed invoices can be reprocessed" in refused.data
    assert _events(app, invoice_id) == before_events  # no audit on refusal


# ---------------------------------------------------------- TC-PIPE-FAIL-07

def test_reprocess_episode_gets_fresh_retry_allowance(
    app, client, worker, make_pdf, monkeypatch
):
    """TC-PIPE-FAIL-07 (review finding M1) — a manual reprocess after an
    exhausted episode receives the FULL configured allowance again, instead
    of inheriting the spent counter. The persisted counter keeps
    accumulating across episodes for observability only."""
    _, pdf_bytes = make_pdf("refail.pdf", pages=1, text_lines=SYNTHETIC_INVOICE)
    client.post(
        "/upload",
        data={"file": (io.BytesIO(pdf_bytes), "refail.pdf")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    invoice_id = _rows(app)[0]["id"]
    stored = app.config["UPLOAD_DIR"] / _rows(app)[0]["stored_filename"]
    stored.unlink()  # episode 1: transient unreadable file
    worker.run_pending()

    row = _rows(app)[0]
    assert row["status"] == "failed"
    assert row["extract_attempts"] == app.config["WORKER_MAX_ATTEMPTS"]

    def always_retryable(invoice_id):
        raise ExtractionRetryable("The stored file could not be read right now.")

    monkeypatch.setattr(extraction, "extract_stored_invoice", always_retryable)
    client.post(f"/invoices/{invoice_id}/reprocess", follow_redirects=True)
    worker.run_pending()

    row = _rows(app)[0]
    assert row["status"] == "failed"
    # Episode 2 got the FULL allowance again: 3 (episode 1) + 3 (episode 2).
    # The pre-fix behaviour inherited the spent counter and would have
    # terminated after a single attempt (column would read 4).
    assert row["extract_attempts"] == 2 * app.config["WORKER_MAX_ATTEMPTS"]

    events = _events(app, invoice_id)
    assert events.count(EVENT_REPROCESS_REQUESTED) == 1
    # exactly one terminal failure pair per episode — bounded retries stay
    # per-episode, audit spam stays away
    assert events.count(EVENT_EXTRACTION_FAILED) == 2
    assert events.count(EVENT_PROCESSING_FAILED) == 2
    assert events.count(EVENT_PROCESSING_STARTED) == 1  # only the first claim
    assert events.count(EVENT_PROCESSING_RESUMED) == 0


# ---------------------------------------------------------- TC-DBLOCK-01..04
# Review finding M2: transient SQLite lock errors during claiming or
# persistence are retried with backoff (bounded by WORKER_DB_MAX_ATTEMPTS);
# non-transient database errors keep the existing containment; exhaustion
# leaves the row eligible for boot-time recovery instead of silently
# dropping the job. Injection point: pipeline.set_extract_attempts (first
# DB write of every attempt) and pipeline.apply_transition (the claim).

def test_transient_db_lock_retried_to_success(app, client, worker, make_pdf, monkeypatch):
    """TC-DBLOCK-01 — one transient lock during persistence is retried and
    the job completes; the retry is logged; nothing is force-failed."""
    _, pdf_bytes = make_pdf("locked.pdf", pages=1, text_lines=SYNTHETIC_INVOICE)
    client.post(
        "/upload",
        data={"file": (io.BytesIO(pdf_bytes), "locked.pdf")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    invoice_id = _rows(app)[0]["id"]

    real_set = pipeline.set_extract_attempts
    calls = {"n": 0}

    def locked_once(conn, invoice_id, attempts):
        calls["n"] += 1
        if calls["n"] == 1:
            raise sqlite3.OperationalError("database is locked")
        return real_set(conn, invoice_id, attempts)

    monkeypatch.setattr(pipeline, "set_extract_attempts", locked_once)
    worker.run_pending()

    row = _rows(app)[0]
    assert row["status"] == "completed"
    assert row["extract_attempts"] == 1  # the locked write rolled back
    logs = applog.events_log_path(app).read_text(encoding="utf-8")
    assert logs.count("event=db_locked_retry") == 1
    assert "event=worker_db_error" not in logs


def test_db_lock_exhaustion_leaves_row_for_boot_recovery(
    app, client, worker, make_pdf, monkeypatch, make_app_config
):
    """TC-DBLOCK-02 — persistent lock errors exhaust the bounded retries;
    the row keeps its eligible status (`processing`) and the documented
    boot-time recovery path completes it afterwards."""
    app.config["WORKER_DB_MAX_ATTEMPTS"] = 2  # small bound for the test
    _, pdf_bytes = make_pdf("jinxed.pdf", pages=1, text_lines=SYNTHETIC_INVOICE)
    client.post(
        "/upload",
        data={"file": (io.BytesIO(pdf_bytes), "jinxed.pdf")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    invoice_id = _rows(app)[0]["id"]

    real_set = pipeline.set_extract_attempts
    calls = {"n": 0}

    def locked_twice(conn, invoice_id, attempts):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise sqlite3.OperationalError("database is locked")
        return real_set(conn, invoice_id, attempts)

    monkeypatch.setattr(pipeline, "set_extract_attempts", locked_twice)
    worker.run_pending()

    row = _rows(app)[0]
    assert row["status"] == "processing"  # eligible — NOT force-failed
    logs = applog.events_log_path(app).read_text(encoding="utf-8")
    assert "reason=db_lock_exhausted" in logs
    assert "event=db_locked_retry" in logs

    # documented recovery path: next boot enqueues a recovery job, the
    # transient condition has cleared, the row completes
    app2 = create_app(make_app_config(database=app.config["DATABASE"]))
    app2.extensions["invoice_worker"].run_pending()

    conn = _open_db(app2)
    try:
        row = get_invoice(conn, invoice_id)
        events = [r["event_type"] for r in get_audit(conn, invoice_id)]
    finally:
        conn.close()
    assert row["status"] == "completed"
    assert events.count(EVENT_PROCESSING_RESUMED) == 1
    assert events.count(EVENT_PROCESSING_STARTED) == 1  # unchanged by recovery


def test_non_transient_db_error_keeps_containment(
    app, client, worker, make_pdf, monkeypatch
):
    """TC-DBLOCK-03 — non-lock database errors are not retried: the existing
    containment applies (raise out of run_pending, logged with
    reason=non_transient) and the row waits for boot-time recovery."""
    _, pdf_bytes = make_pdf("nope.pdf", pages=1, text_lines=SYNTHETIC_INVOICE)
    client.post(
        "/upload",
        data={"file": (io.BytesIO(pdf_bytes), "nope.pdf")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    invoice_id = _rows(app)[0]["id"]

    def no_such_table(conn, invoice_id, attempts):
        raise sqlite3.OperationalError("no such table: invoices")

    monkeypatch.setattr(pipeline, "set_extract_attempts", no_such_table)
    with pytest.raises(sqlite3.OperationalError):
        worker.run_pending()

    row = _rows(app)[0]
    assert row["status"] == "processing"  # eligible for boot recovery
    logs = applog.events_log_path(app).read_text(encoding="utf-8")
    assert "reason=non_transient" in logs
    assert "event=db_locked_retry" not in logs  # never retried


def test_claim_lock_retried_without_duplicate_t1(app, worker, make_pdf, monkeypatch):
    """TC-DBLOCK-04 — a lock during the claim itself is retried cleanly:
    the rolled-back T1 is performed once (no duplicate
    processing_started) and the pipeline completes."""
    _, pdf_bytes = make_pdf("claimlock.pdf", pages=1, text_lines=SYNTHETIC_INVOICE)
    stored_name = "uuid-claimlock.pdf"
    (app.config["UPLOAD_DIR"] / stored_name).write_bytes(pdf_bytes)
    with app.app_context():
        invoice_id = insert_invoice(
            conn=get_db(),
            file_hash="hash-claimlock",
            original_filename="claimlock.pdf",
            stored_filename=stored_name,
            status="uploaded",
            page_count=1,
        )

    real_apply = pipeline.apply_transition
    calls = {"n": 0}

    def locked_on_first_claim(conn, invoice_id, action):
        calls["n"] += 1
        if calls["n"] == 1:
            raise sqlite3.OperationalError("database is locked")
        return real_apply(conn, invoice_id, action)

    monkeypatch.setattr(pipeline, "apply_transition", locked_on_first_claim)
    worker.process_job(invoice_id, JOB_NEW_UPLOAD)

    row = _rows(app)[0]
    assert row["status"] == "completed"
    events = _events(app, invoice_id)
    assert events.count(EVENT_PROCESSING_STARTED) == 1  # rolled-back T1 not duplicated
    assert events.count(EVENT_EXTRACTION_COMPLETED) == 1
    assert events.count(EVENT_PROCESSING_COMPLETED) == 1
    logs = applog.events_log_path(app).read_text(encoding="utf-8")
    assert "event=db_locked_retry" in logs


# ---------------------------------------------------------------- TC-RECV-01

def test_recovery_uploaded_stalled(app, make_app_config, make_pdf):
    """TC-RECV-01 — a row stuck in `uploaded` (crash before pickup) is
    completed by the next boot's recovery job; recovery itself writes no
    audit rows; processing_started appears exactly once."""
    app1 = create_app(make_app_config())
    _, pdf_bytes = make_pdf("stalled.pdf", pages=1, text_lines=SYNTHETIC_INVOICE)
    stored_name = "uuid-stalled.pdf"
    (app1.config["UPLOAD_DIR"] / stored_name).write_bytes(pdf_bytes)
    with app1.app_context():
        invoice_id = insert_invoice(
            conn=get_db(),
            file_hash="hash-stalled",
            original_filename="stalled.pdf",
            stored_filename=stored_name,
            status="uploaded",
            page_count=1,
        )

    app2 = create_app(make_app_config(database=app1.config["DATABASE"]))
    assert app2.extensions["invoice_worker"].queued_count() == 1  # recovery job
    app2.extensions["invoice_worker"].run_pending()

    conn = _open_db(app2)
    try:
        row = get_invoice(conn, invoice_id)
        events = [r["event_type"] for r in get_audit(conn, invoice_id)]
    finally:
        conn.close()
    assert row["status"] == "completed"
    assert events == [
        # NOTE: no invoice_uploaded — this row was seeded directly, not via
        # the upload route; recovery itself wrote no audit rows.
        EVENT_PROCESSING_STARTED,  # exactly once — by the recovery job's claim
        EVENT_EXTRACTION_COMPLETED,
        EVENT_PROCESSING_COMPLETED,
    ]
    assert events.count(EVENT_PROCESSING_STARTED) == 1
    assert EVENT_PROCESSING_RESUMED not in events


# ---------------------------------------------------------------- TC-RECV-02

def test_recovery_processing_stalled(app, make_app_config, make_pdf):
    """TC-RECV-02 — a row stuck in `processing` with a pre-existing
    processing_started event is resumed exactly once; no duplicate
    processing_started; recovery writes no audit rows itself."""
    app1 = create_app(make_app_config())
    invoice_id = _seed_processing_invoice(app1, make_pdf)
    events_before = _events(app1, invoice_id)
    assert events_before == [EVENT_PROCESSING_STARTED]

    app2 = create_app(make_app_config(database=app1.config["DATABASE"]))
    app2.extensions["invoice_worker"].run_pending()

    conn = _open_db(app2)
    try:
        row = get_invoice(conn, invoice_id)
        events = [r["event_type"] for r in get_audit(conn, invoice_id)]
    finally:
        conn.close()
    assert row["status"] == "completed"
    assert events.count(EVENT_PROCESSING_STARTED) == 1  # no duplicate
    assert events.count(EVENT_PROCESSING_RESUMED) == 1  # exactly one resume
    assert events == [
        EVENT_PROCESSING_STARTED,
        EVENT_PROCESSING_RESUMED,
        EVENT_EXTRACTION_COMPLETED,
        EVENT_PROCESSING_COMPLETED,
    ]


# ---------------------------------------------------------------- TC-RECV-03

def test_normal_job_never_resumes_processing(app, worker, make_pdf):
    """TC-RECV-03 — ownership rule: a normal job encountering a `processing`
    invoice skips without resuming it; only the recovery-designated job
    resumes."""
    invoice_id = _seed_processing_invoice(app, make_pdf)
    before = _events(app, invoice_id)

    worker.process_job(invoice_id, JOB_NEW_UPLOAD)  # normal job: must skip

    mid = _events(app, invoice_id)
    assert mid == before  # no events, no resume, status unchanged
    assert _rows(app)[0]["status"] == "processing"

    worker.process_job(invoice_id, JOB_RECOVERY)  # recovery job: may resume
    row = _rows(app)[0]
    assert row["status"] == "completed"
    after = _events(app, invoice_id)
    assert after.count(EVENT_PROCESSING_STARTED) == 1
    assert after.count(EVENT_PROCESSING_RESUMED) == 1


# ---------------------------------------------------------------- TC-RECV-04

def test_duplicate_jobs_and_healthy_boot(app, worker, make_pdf, make_app_config):
    """TC-RECV-04 — unexpected duplicate job prevention and healthy-boot
    behaviour: (a) a second enqueue of the same invoice is a no-op whatever
    the kind; (b) a stale recovery job delivered to a terminal invoice skips
    without events; (c) a boot with nothing stalled enqueues nothing."""
    # (c) healthy boot: all rows terminal → no recovery jobs
    app_healthy = create_app(make_app_config())
    assert app_healthy.extensions["invoice_worker"].queued_count() == 0

    # (a) duplicate enqueue prevention
    _, pdf_bytes = make_pdf("dup.pdf", pages=1, text_lines=SYNTHETIC_INVOICE)
    stored_name = "uuid-dup.pdf"
    (app.config["UPLOAD_DIR"] / stored_name).write_bytes(pdf_bytes)
    with app.app_context():
        invoice_id = insert_invoice(
            conn=get_db(),
            file_hash="hash-dup",
            original_filename="dup.pdf",
            stored_filename=stored_name,
            status="uploaded",
            page_count=1,
        )
    assert worker.enqueue(invoice_id, JOB_RECOVERY) is True
    assert worker.enqueue(invoice_id, JOB_NEW_UPLOAD) is False  # duplicate: no-op
    assert worker.enqueue(invoice_id, JOB_RECOVERY) is False  # duplicate: no-op
    assert worker.queued_count() == 1

    worker.run_pending()
    assert _rows(app)[0]["status"] == "completed"
    assert _events(app, invoice_id).count(EVENT_PROCESSING_STARTED) == 1

    # (b) stale recovery job delivered after completion: skips, no events
    events_before = _events(app, invoice_id)
    worker.process_job(invoice_id, JOB_RECOVERY)
    assert _events(app, invoice_id) == events_before
    assert _rows(app)[0]["status"] == "completed"


# ---------------------------------------------------------------- TC-ERR-500

def test_generic_500_no_leak(app, client):
    """TC-ERR-500-01 — an unhandled exception yields a generic error page;
    the exception text never reaches the response or either log file."""
    app.config["PROPAGATE_EXCEPTIONS"] = False

    def boom():
        raise RuntimeError("SENTINEL-500-DETAILS")

    app.add_url_rule("/boom", "boom", boom)
    response = client.get("/boom")
    assert response.status_code == 500
    assert b"unexpected error" in response.data
    assert b"SENTINEL-500-DETAILS" not in response.data

    events = applog.events_log_path(app).read_text(encoding="utf-8")
    errors = applog.errors_log_path(app).read_text(encoding="utf-8")
    assert "event=unhandled_error" in events
    assert "error_class=RuntimeError" in events
    assert "SENTINEL-500-DETAILS" not in events
    assert "an unexpected error occurred" in errors
    assert "SENTINEL-500-DETAILS" not in errors
    assert "Traceback" not in errors  # unsanitised tracebacks are never logged


# ---------------------------------------------------------------- TC-LOG-01

def test_logs_never_contain_invoice_content(app, client, worker, make_pdf):
    """TC-LOG-01 — a full pipeline run leaves no invoice content in either
    log; events carry structured allowlisted fields only."""
    sentinel_invoice = SYNTHETIC_INVOICE + ["CONFIDENTIAL-SENTINEL-LINE"]
    _upload(client, make_pdf, "logged.pdf", text_lines=sentinel_invoice)
    worker.run_pending()

    events = applog.events_log_path(app).read_text(encoding="utf-8")
    errors = applog.errors_log_path(app).read_text(encoding="utf-8")
    for leak in ("CONFIDENTIAL-SENTINEL-LINE", "INV-E1-0001",
                 "Acme Corporation", "extraction_json"):
        assert leak not in events, leak
        assert leak not in errors, leak
    assert "event=pipeline_completed" in events
    assert "invoice_id=" in events


def test_log_event_rejects_non_allowlisted_field():
    """TC-LOG-01b — the structural guarantee: free-form fields cannot enter
    the events log because log_event refuses them."""
    with pytest.raises(ValueError):
        applog.log_event("probe", message_text="should never be allowed")
