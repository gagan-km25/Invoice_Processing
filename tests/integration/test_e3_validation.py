"""Sprint E3 integration tests — validation + duplicates in the pipeline.

The pipeline runs end-to-end with `extraction.extract_stored_invoice`
stubbed to persist crafted drafts, so verdicts/classifications are driven
deterministically without any AI or parser text-matching dependencies
(WORKER_AUTOSTART=False; tests drain the queue via `worker.run_pending()`).
"""
import io
import json
import sqlite3

from werkzeug.datastructures import FileStorage

from app.db import get_db
from app.db.repository import get_audit, insert_invoice
from app.services import extraction
from app.services.audit import EVENT_DUPLICATE_DETECTED

DRAFT_META = {"page_count": 1, "parser_version": 1, "source": "stub"}


def _field(value):
    return {"status": "found", "value": value}


def _valid_draft(**overrides):
    """A draft that passes every §8 rule: mandatory fields present,
    100.00 + 8.00 = 108.00, lines sum to the subtotal, dates sane."""
    fields = {
        "invoice_number": _field("INV-E3-0001"),
        "invoice_date": _field("2026-09-30"),
        "vendor": _field("Acme Corporation"),
        "currency": _field("USD"),
        "subtotal": _field("100.00"),
        "tax": _field("8.00"),
        "total": _field("108.00"),
    }
    fields.update(overrides)
    return {
        "fields": fields,
        "lines": [{"line_number": 1, "description": "Widget",
                   "quantity": "2", "unit_price": "50.00",
                   "amount": "100.00", "tax": None}],
        "checks": [],
        "meta": dict(DRAFT_META),
    }


def _conn(app):
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    return conn


def _row(app, invoice_id):
    conn = _conn(app)
    try:
        return conn.execute(
            "SELECT * FROM invoices WHERE id = ?", (invoice_id,)
        ).fetchone()
    finally:
        conn.close()


def _events(app, invoice_id):
    return [row["event_type"] for row in get_audit(_conn(app), invoice_id)]


def _stub_extraction(monkeypatch, drafts):
    """extract_stored_invoice → persist the next crafted draft, in order."""
    drafts = list(drafts)

    def fake(invoice_id):
        draft = drafts.pop(0)
        conn = get_db()
        try:
            from app.db.repository import update_extraction

            update_extraction(conn, invoice_id, draft=draft, write_lines=True)
        finally:
            conn.close()
        return True, "stubbed extraction"

    monkeypatch.setattr(extraction, "extract_stored_invoice", fake)


def _upload(client, pdf_storage, name="e3.pdf"):
    storage: FileStorage = pdf_storage(name)
    return client.post(
        "/upload",
        data={"file": (io.BytesIO(storage.read()), name)},
        content_type="multipart/form-data",
        follow_redirects=True,
    )


# ------------------------------------------------------- pipeline: verdicts

def test_valid_invoice_completes_with_passed_verdict(
    app, client, worker, pdf_storage, monkeypatch
):
    """TC-E3-V01 — a clean draft: completed (T2), validation_status
    'passed', findings '[]', duplicate classification 'none' persisted."""
    _stub_extraction(monkeypatch, [_valid_draft()])
    _upload(client, pdf_storage)
    assert worker.run_pending() == 1

    row = _row(app, 1)
    assert row["status"] == "completed"
    assert row["validation_status"] == "passed"
    assert json.loads(row["validation_json"]) == []
    assert row["dup_status"] == "none"
    assert json.loads(row["dup_matches"]) == []


def test_error_verdict_transitions_to_validation_failed(
    app, client, worker, pdf_storage, monkeypatch
):
    """TC-E3-V02 — error findings (T3): status validation_failed, findings
    JSON persisted with codes, audit entry written."""
    draft = _valid_draft()
    draft["fields"].pop("currency")
    draft["fields"]["total"] = _field("999.00")  # primary equation breaks too
    _stub_extraction(monkeypatch, [draft])
    _upload(client, pdf_storage)
    assert worker.run_pending() == 1

    row = _row(app, 1)
    assert row["status"] == "validation_failed"
    assert row["validation_status"] == "failed"
    codes = [f["code"] for f in json.loads(row["validation_json"])]
    assert "E_MISSING_CURRENCY" in codes
    assert "E_AMOUNT_PRIMARY_MISMATCH" in codes
    assert "validation_failed" in _events(app, 1)


def test_warning_verdict_still_completes(
    app, client, worker, pdf_storage, monkeypatch
):
    """TC-E3-V03 — warnings never block (approved decision 1): a malformed
    GSTIN yields verdict 'warning' and the record still completes."""
    draft = _valid_draft(
        vendor_tax_id=_field("NOT-A-GSTIN"),
        discount=_field("10.00"),  # discount-aware equation mismatch too
    )
    _stub_extraction(monkeypatch, [draft])
    _upload(client, pdf_storage)
    assert worker.run_pending() == 1

    row = _row(app, 1)
    assert row["status"] == "completed"
    assert row["validation_status"] == "warning"
    codes = [f["code"] for f in json.loads(row["validation_json"])]
    assert "W_GSTIN_FORMAT" in codes
    assert "W_DISCOUNT_EQUATION" in codes


def test_reprocess_from_validation_failed_succeeds(
    app, client, worker, pdf_storage, monkeypatch
):
    """TC-E3-V04 — T5b: reprocess claims a validation_failed record
    (audit reprocess_requested) and a now-valid draft completes it."""
    bad = _valid_draft()
    bad["fields"].pop("vendor")
    _stub_extraction(monkeypatch, [bad])
    _upload(client, pdf_storage)
    assert worker.run_pending() == 1
    assert _row(app, 1)["status"] == "validation_failed"

    _stub_extraction(monkeypatch, [_valid_draft()])
    client.post("/invoices/1/reprocess", follow_redirects=True)
    assert worker.run_pending() == 1

    row = _row(app, 1)
    assert row["status"] == "completed"
    assert row["validation_status"] == "passed"
    assert "reprocess_requested" in _events(app, 1)


def test_validation_failed_record_is_not_reviewable(
    app, client, worker, pdf_storage, monkeypatch
):
    """TC-E3-V05 — the review surface stays completed/extracted; a
    validation_failed record is corrected by reprocessing, not review."""
    bad = _valid_draft()
    bad["fields"].pop("total")
    _stub_extraction(monkeypatch, [bad])
    _upload(client, pdf_storage)
    assert worker.run_pending() == 1
    assert _row(app, 1)["status"] == "validation_failed"

    response = client.get("/invoices/1/review")
    assert response.status_code == 302  # redirected away with a flash


# --------------------------------------------------- pipeline: duplicates

def test_exact_duplicate_detected_and_audited(
    app, client, worker, pdf_storage, monkeypatch
):
    """TC-E3-D01 — a second upload with the same vendor + number
    classifies as an exact duplicate; the audit event fires."""
    _stub_extraction(monkeypatch, [_valid_draft()])
    _upload(client, pdf_storage, "first.pdf")
    assert worker.run_pending() == 1
    assert _row(app, 1)["dup_status"] == "none"  # nothing to match yet

    second = _valid_draft(invoice_number=_field("INV-E3-0001"))
    _stub_extraction(monkeypatch, [second])
    _upload(client, pdf_storage, "second.pdf")
    assert worker.run_pending() == 1

    row = _row(app, 2)
    assert row["status"] == "completed"  # informational — never blocking
    assert row["dup_status"] == "exact"
    matches = json.loads(row["dup_matches"])
    assert [match["id"] for match in matches] == [1]
    assert matches[0]["kind"] == "exact"
    assert EVENT_DUPLICATE_DETECTED in _events(app, 2)
    assert EVENT_DUPLICATE_DETECTED not in _events(app, 1)


def test_possible_duplicate_classified(
    app, client, worker, pdf_storage, monkeypatch
):
    """TC-E3-D02 — same vendor + total + date, different number → possible."""
    _stub_extraction(monkeypatch, [_valid_draft()])
    _upload(client, pdf_storage, "first.pdf")
    assert worker.run_pending() == 1

    second = _valid_draft(invoice_number=_field("INV-E3-0002"))
    _stub_extraction(monkeypatch, [second])
    _upload(client, pdf_storage, "second.pdf")
    assert worker.run_pending() == 1

    row = _row(app, 2)
    assert row["dup_status"] == "possible"
    match = json.loads(row["dup_matches"])[0]
    assert match["id"] == 1
    assert match["kind"] == "possible"


def test_duplicate_detection_ignores_draft_states(
    app, pdf_storage, monkeypatch
):
    """TC-E3-D03 — an `uploaded` row (no comparable fields yet) is never a
    candidate: classifying a completed invoice against it finds nothing."""
    from app.db.repository import set_duplicate_classification
    from app.services import duplicates

    _seed_uploaded(app)                       # id 1: stays `uploaded`
    completed = _seed_completed(app, monkeypatch, pdf_storage)  # id 2

    with app.app_context():
        conn = get_db()
        try:
            result = duplicates.classify(conn, completed)
            set_duplicate_classification(
                conn, completed, result["classification"],
                json.dumps(result["matches"]),
            )
        finally:
            conn.close()
    row = _row(app, completed)
    assert row["dup_status"] == "none"


# ------------------------------------------------------ detail page (§14)

def test_detail_page_shows_validation_findings(
    app, client, worker, pdf_storage, monkeypatch
):
    """TC-E3-U01 — the detail page renders the verdict and each finding
    message for a failed validation."""
    bad = _valid_draft()
    bad["fields"].pop("currency")
    _stub_extraction(monkeypatch, [bad])
    _upload(client, pdf_storage)
    assert worker.run_pending() == 1

    html = client.get("/invoices/1").data.decode()
    assert "validation_failed" in html
    assert "Currency is required." in html


def test_detail_page_shows_duplicate_explanation(
    app, client, worker, pdf_storage, monkeypatch
):
    """TC-E3-U02 — the detail page names the matched record (§9: stored
    explanation) for an exact duplicate."""
    _stub_extraction(monkeypatch, [_valid_draft()])
    _upload(client, pdf_storage, "first.pdf")
    worker.run_pending()

    _stub_extraction(monkeypatch, [_valid_draft()])
    _upload(client, pdf_storage, "second.pdf")
    worker.run_pending()

    html = client.get("/invoices/2").data.decode()
    assert "Duplicate check" in html
    assert "exact duplicate" in html
    assert "Same vendor and invoice number as" in html
    assert "/invoices/1" in html


def test_detail_page_hides_duplicate_panel_when_none(
    app, client, worker, pdf_storage, monkeypatch
):
    """TC-E3-U03 — no duplicate noise when the classification is none."""
    _stub_extraction(monkeypatch, [_valid_draft()])
    _upload(client, pdf_storage)
    worker.run_pending()

    html = client.get("/invoices/1").data.decode()
    assert "Duplicate check" not in html
    assert "Validation" in html  # the verdict panel still shows


# ----------------------------------------------------------------- seeds

def _seed_uploaded(app):
    """Insert an `uploaded` row directly (no queue entry — nothing will
    drain it); returns its id."""
    with app.app_context():
        return insert_invoice(
            get_db(),
            file_hash="hash-uploaded",
            original_filename="busy.pdf",
            stored_filename="uuid-busy.pdf",
            status="uploaded",
            page_count=1,
        )


def _seed_completed(app, monkeypatch, pdf_storage):
    """Upload + drain with a valid draft → a `completed` row with fields."""
    def fake(invoice_id):
        conn = get_db()
        try:
            from app.db.repository import update_extraction

            update_extraction(conn, invoice_id, draft=_valid_draft(),
                              write_lines=True)
        finally:
            conn.close()
        return True, "stubbed"

    monkeypatch.setattr(extraction, "extract_stored_invoice", fake)
    with app.test_client() as client:
        storage = pdf_storage("done.pdf")
        client.post(
            "/upload",
            data={"file": (io.BytesIO(storage.read()), "done.pdf")},
            content_type="multipart/form-data",
        )
    app.extensions["invoice_worker"].run_pending()
    return 2
