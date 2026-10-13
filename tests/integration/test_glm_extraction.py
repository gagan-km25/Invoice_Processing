"""Sprint E2 integration tests — GLM extraction paths, image uploads,
fallback behavior, raw retention, and secret safety.

HTTP is mocked at `glm_client.http_post_json` (single seam) — the suite
never touches the network and requires no API key. The configured key is
the fake sentinel `test-key-zai`.
"""
import base64
import io
import json
import sqlite3
from decimal import Decimal

import pytest

from app.services import applog, extraction, glm_client
from app.services.extraction import (
    _INVALID_AI_MESSAGE,
    _NO_KEY_IMAGE_MESSAGE,
    _NO_KEY_SCAN_MESSAGE,
)

KEY = "test-key-zai"


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

SYNTHETIC = [
    "TAX INVOICE",
    "Acme Corporation Invoice No: INV-G-1",
    "1 Main Street, Springfield Invoice Date: 2026-01-15",
    "Subtotal $1,000.00",
    "Tax (8%) $80.00",
    "Grand Total $1,080.00",
]

VALID_GLM_JSON = json.dumps(
    {
        "invoice_number": "INV-G-1",
        "invoice_date": "2026-01-15",
        "due_date": None,
        "vendor": "Acme Corporation",
        "vendor_tax_id": None,
        "bill_to": None,
        "currency": "USD",
        "subtotal": 1000,
        "discount": None,
        "tax": 80,
        "tax_rate": 8,
        "total": 1080,
        "line_items": [
            {"description": "Item A", "quantity": 2, "unit_price": 40, "amount": 80}
        ],
    }
)


def _png_bytes() -> bytes:
    """Minimal content-signature-valid PNG (gates/extraction treat it as an
    image; the vision model is stubbed so no real decoding is needed)."""
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 48


def _rows(app, query="SELECT * FROM invoices ORDER BY id"):
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(query).fetchall()
    finally:
        conn.close()


def _upload(app, client, name, data):
    return client.post(
        "/upload",
        data={"file": (io.BytesIO(data), name)},
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def _configure_key(app):
    app.config["ZAI_API_KEY"] = KEY


def _stub_glm(monkeypatch, content):
    """Stub the transport to return `content`; capture request payloads."""
    captured = {}

    def fake_post(url, *, headers, payload, timeout):
        captured["payload"] = payload
        captured["headers"] = headers
        return _FakeResponse(200, _glm_payload(content))

    monkeypatch.setattr(glm_client, "http_post_json", fake_post)
    return captured


def _glm_payload(content):
    return {"choices": [{"message": {"content": content}}]}


def _events(app, invoice_id):
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    try:
        return [
            r["event_type"]
            for r in conn.execute(
                "SELECT event_type FROM invoice_audit WHERE invoice_id = ? ORDER BY id",
                (invoice_id,),
            ).fetchall()
        ]
    finally:
        conn.close()


# ---------------------------------------------------------- TC-GLM-TEXT-01

def test_glm_text_extraction_completes(app, client, worker, make_pdf, monkeypatch):
    """TC-GLM-TEXT-01 — configured key + text PDF → GLM text path with JSON
    mode; draft persisted with source=glm; raw response retained."""
    _configure_key(app)
    _, pdf_bytes = make_pdf("glm.pdf", pages=1, text_lines=SYNTHETIC)
    response = _upload(app, client, "glm.pdf", pdf_bytes)
    assert response.status_code == 200
    invoice_id = _rows(app)[0]["id"]

    captured = _stub_glm(monkeypatch, VALID_GLM_JSON)
    worker.run_pending()

    row = _rows(app)[0]
    assert row["status"] == "completed"
    assert row["invoice_number"] == "INV-G-1"
    assert row["raw_response"] == VALID_GLM_JSON  # under the cap → verbatim
    draft = json.loads(row["extraction_json"])
    assert draft["meta"]["source"] == "glm"
    assert draft["meta"]["model"] == app.config["ZAI_TEXT_MODEL"]
    assert Decimal(str(draft["fields"]["subtotal"]["value"])) == Decimal("1000.00")
    assert _events(app, invoice_id) == [
        "invoice_uploaded",
        "processing_started",
        "extraction_completed",
        "processing_completed",
    ]
    # request shape: JSON mode on, key in the auth header only, configured
    # output cap present (M-B)
    assert captured["payload"]["response_format"] == {"type": "json_object"}
    assert captured["payload"]["max_tokens"] == app.config["ZAI_MAX_TOKENS"]
    assert captured["headers"]["Authorization"] == f"Bearer {KEY}"


# ---------------------------------------------------------- TC-GLM-VISION-02

def test_glm_vision_image_upload(app, client, worker, monkeypatch):
    """TC-GLM-VISION-02 — a PNG upload goes down the vision path (base64
    image_url) and completes; the original is served as image/png."""
    _configure_key(app)
    response = _upload(app, client, "scan.png", _png_bytes())
    assert response.status_code == 200
    invoice_id = _rows(app)[0]["id"]

    captured = _stub_glm(monkeypatch, VALID_GLM_JSON)
    worker.run_pending()

    row = _rows(app)[0]
    assert row["status"] == "completed"
    assert row["file_type"] == "image"
    assert draft_meta_source(row) == "glm"

    original = client.get(f"/invoices/{invoice_id}/original")
    assert original.headers["Content-Type"].startswith("image/png")

    parts = captured["payload"]["messages"][0]["content"]
    image_parts = [p for p in parts if p["type"] == "image_url"]
    assert len(image_parts) == 1
    assert image_parts[0]["image_url"]["url"].startswith("data:image/png;base64,")
    # H-1: the vision path must call the VISION model, not the text model
    assert captured["payload"]["model"] == app.config["ZAI_VISION_MODEL"]


def draft_meta_source(row):
    return json.loads(row["extraction_json"])["meta"]["source"]


# ---------------------------------------------------------- TC-GLM-SCAN-03

def test_scanned_pdf_rasterizes_max_pages(app, client, worker, monkeypatch, make_pdf):
    """TC-GLM-SCAN-03 — a 5-page scanned PDF sends at most VISION_MAX_PAGES
    (3) rasterized pages to the vision model."""
    _configure_key(app)
    _, pdf_bytes = make_pdf("scan5.pdf", pages=5)  # no text layer → scan
    response = _upload(app, client, "scan5.pdf", pdf_bytes)
    invoice_id = _rows(app)[0]["id"]

    captured = _stub_glm(monkeypatch, VALID_GLM_JSON)
    worker.run_pending()

    row = _rows(app)[0]
    assert row["status"] == "completed"
    parts = captured["payload"]["messages"][0]["content"]
    image_parts = [p for p in parts if p["type"] == "image_url"]
    assert len(image_parts) == app.config["VISION_MAX_PAGES"] == 3
    for part in image_parts:
        assert part["image_url"]["url"].startswith("data:image/png;base64,")


# ---------------------------------------------------------- TC-RESP-01/02

def test_malformed_response_reask_then_permanent(
    app, client, worker, make_pdf, monkeypatch
):
    """TC-RESP-01/02 — a malformed GLM response triggers exactly one
    re-ask; a persistently malformed response fails the invoice with the
    safe message and retains the raw response for troubleshooting."""
    _configure_key(app)
    _, pdf_bytes = make_pdf("mal.pdf", pages=1, text_lines=SYNTHETIC)
    response = _upload(app, client, "mal.pdf", pdf_bytes)
    invoice_id = _rows(app)[0]["id"]

    sentinel_raw = "SENTINEL-RAW-NOT-JSON"
    monkeypatch.setattr(
        glm_client, "http_post_json", lambda *a, **k: _always(sentinel_raw)
    )

    worker.run_pending()

    row = _rows(app)[0]
    assert row["status"] == "failed"
    assert row["error_message"] == extraction._INVALID_AI_MESSAGE
    assert row["raw_response"] == sentinel_raw  # retained locally
    events = _events(app, invoice_id)
    assert events.count("extraction_failed") == 1
    assert events.count("processing_failed") == 1


def _always(content):
    class _Response:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": content}}]}

    return _Response()


# ---------------------------------------------------------- TC-GLM-UNAVAIL

def test_transient_unavailability_exhausts_and_marks_failed(
    app, client, worker, make_pdf, monkeypatch
):
    """TC-GLM-UNAVAIL-01 — persistent HTTP 503 is retryable; after the bound
    the invoice is `failed` with the safe HTTP-status message."""
    _configure_key(app)
    _, pdf_bytes = make_pdf("down.pdf", pages=1, text_lines=SYNTHETIC)
    _upload(app, client, "down.pdf", pdf_bytes)
    invoice_id = _rows(app)[0]["id"]

    class _Response:
        status_code = 503

        def json(self):
            return {}

    def always_503(url, *, headers, payload, timeout):
        return _Response()

    monkeypatch.setattr(glm_client, "http_post_json", always_503)
    worker.run_pending()

    row = _rows(app)[0]
    assert row["status"] == "failed"
    assert row["extract_attempts"] == app.config["WORKER_MAX_ATTEMPTS"]
    assert "HTTP 503" in row["error_message"]
    # retry attempts are structured log events, not audit rows
    logs = applog.events_log_path(app).read_text(encoding="utf-8")
    assert logs.count("event=extraction_retryable") == app.config["WORKER_MAX_ATTEMPTS"]
    assert _events(app, invoice_id).count("extraction_retryable") == 0


# ---------------------------------------------------------- TC-FALLBACK-01

def test_unconfigured_text_pdf_uses_local_parser(app, client, worker, make_pdf):
    """TC-FALLBACK-01 — no API key + text PDF → existing local parser path
    completes and the draft is not marked as GLM-sourced."""
    _, pdf_bytes = make_pdf("local.pdf", pages=1, text_lines=SYNTHETIC)
    response = _upload(app, client, "local.pdf", pdf_bytes)
    assert response.status_code == 200
    worker.run_pending()

    row = _rows(app)[0]
    assert row["status"] == "completed"
    assert row["invoice_number"] == "INV-G-1"
    draft = json.loads(row["extraction_json"])
    assert draft["meta"].get("source") != "glm"


def test_unconfigured_image_fails_with_clear_message(app, client, worker):
    """TC-FALLBACK-02 — images require GLM: unconfigured → clear permanent
    failure, never a local-parser misparse."""
    response = _upload(app, client, "photo.png", _png_bytes())
    assert response.status_code == 200
    worker.run_pending()

    row = _rows(app)[0]
    assert row["status"] == "failed"
    assert "AI extraction" in row["error_message"]
    assert "not configured" in row["error_message"]


def test_unconfigured_scanned_pdf_fails_with_clear_message(
    app, client, worker, make_pdf
):
    """TC-FALLBACK-03 — unconfigured + scanned PDF → clear permanent
    failure (scans require GLM per decision 1)."""
    _, pdf_bytes = make_pdf("blank.pdf", pages=1)  # no text layer
    _upload(app, client, "blank.pdf", pdf_bytes)
    worker.run_pending()

    row = _rows(app)[0]
    assert row["status"] == "failed"
    assert "likely a scan" in row["error_message"]
    assert "not configured" in row["error_message"]


# ---------------------------------------------------------- TC-KEY-01

def test_api_key_never_leaks(app, client, worker, make_pdf, monkeypatch):
    """TC-KEY-01 — a 401 from the provider must not leak the key into the
    record, the response, or either log file."""
    _configure_key(app)
    _, pdf_bytes = make_pdf("auth.pdf", pages=1, text_lines=SYNTHETIC)
    _upload(app, client, "auth.pdf", pdf_bytes)
    invoice_id = _rows(app)[0]["id"]

    class _Response:
        status_code = 401

        def json(self):
            return {"error": {"message": "invalid key: test-key-zai"}}

    monkeypatch.setattr(
        glm_client, "http_post_json", lambda *a, **k: _Response()
    )
    worker.run_pending()

    row = _rows(app)[0]
    assert row["status"] == "failed"
    assert KEY not in (row["error_message"] or "")
    events = applog.events_log_path(app).read_text(encoding="utf-8")
    errors = applog.errors_log_path(app).read_text(encoding="utf-8")
    assert KEY not in events
    assert KEY not in errors


# ---------------------------------------------------------- TC-RAW-01

def test_raw_response_truncated_to_cap(app, client, worker, make_pdf, monkeypatch):
    """TC-RAW-01 — oversized raw responses are truncated at the configured
    cap (with a marker) before storage."""
    _configure_key(app)
    app.config["RAW_RESPONSE_MAX_BYTES"] = 64
    huge_obj = json.loads(VALID_GLM_JSON)
    huge_obj["vendor"] = "Acme Corporation " + "X" * 500  # valid JSON, > cap
    huge_content = json.dumps(huge_obj)
    _stub_glm(monkeypatch, huge_content)
    _, pdf_bytes = make_pdf("big.pdf", pages=1, text_lines=SYNTHETIC)
    _upload(app, client, "big.pdf", pdf_bytes)
    worker.run_pending()

    row = _rows(app)[0]
    assert row["status"] == "completed"
    assert len(row["raw_response"].encode("utf-8")) <= 64 + 20  # cap + marker
    assert "[truncated]" in row["raw_response"]


# ---------------------------------------------------------- TC-DBLOCK-05 (M-A)

def test_rasterize_failure_is_safe_permanent(app, client, worker, make_pdf, monkeypatch):
    """TC-DBLOCK-05 (M-A) — a scanned PDF that pdfium cannot render fails
    permanently with the user-safe message instead of a generic crash; the
    underlying error class never reaches the record."""
    _configure_key(app)
    _, pdf_bytes = make_pdf("unrenderable.pdf", pages=1)  # no text → scan path

    import pypdfium2 as pdfium_mod
    from pypdfium2._helpers.misc import PdfiumError

    def failing_rasterize(data, max_pages):
        raise PdfiumError("Failed to load page.")

    monkeypatch.setattr(extraction, "_rasterize_pdf", failing_rasterize)
    response = _upload(app, client, "unrenderable.pdf", pdf_bytes)
    assert response.status_code == 200
    worker.run_pending()

    row = _rows(app)[0]
    assert row["status"] == "failed"
    assert "could not be converted for vision" in row["error_message"]
    assert "PdfiumError" not in (row["error_message"] or "")
    logs = applog.events_log_path(app).read_text(encoding="utf-8")
    assert "event=extraction_permanent" in logs


# ---------------------------------------------------------- TC-RAW-03 (L-B)

def test_local_fallback_clears_stale_glm_raw(
    app, client, worker, make_pdf, monkeypatch
):
    """TC-RAW-03 (L-B) — a GLM failure retains its raw response, and a later
    local-parser run on the same invoice clears it: the stored raw must
    always match the extraction source."""
    _configure_key(app)
    _, pdf_bytes = make_pdf("mixed.pdf", pages=1, text_lines=SYNTHETIC)
    _upload(app, client, "mixed.pdf", pdf_bytes)
    invoice_id = _rows(app)[0]["id"]

    class _Response:
        status_code = 401

        def json(self):
            return {"error": {"message": "bad key"}}

    monkeypatch.setattr(glm_client, "http_post_json", lambda *a, **k: _Response())
    worker.run_pending()
    row = _rows(app)[0]
    assert row["status"] == "failed"
    # simulate a prior GLM raw retention, then unconfigure for the fallback
    conn = sqlite3.connect(app.config["DATABASE"])
    try:
        conn.execute(
            "UPDATE invoices SET raw_response = 'STALE-GLM-RAW' WHERE id = ?",
            (invoice_id,),
        )
        conn.commit()
    finally:
        conn.close()

    app.config["ZAI_API_KEY"] = ""  # decision 1: unconfigured → local parser
    client.post(f"/invoices/{invoice_id}/reprocess", follow_redirects=True)
    worker.run_pending()

    row = _rows(app)[0]
    assert row["status"] == "completed"  # local parser handled the text PDF
    assert not row["raw_response"]  # stale GLM raw cleared (L-B)
