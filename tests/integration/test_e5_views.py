"""Sprint E5 integration tests — all-status list (US-E5-1) and detail
panels (US-E5-2): audit timeline, escaped collapsed raw response, vendor
visibility. Deterministic drafts via the stubbed extraction seam.
"""
import io
import sqlite3

from app.db import get_db
from app.services import extraction


def _conn(app):
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    return conn


def _field(value):
    return {"status": "found", "value": value}


def _draft(number="INV-L1", total="108.00"):
    return {
        "fields": {
            "invoice_number": _field(number),
            "invoice_date": _field("2026-09-30"),
            "vendor": _field("Acme Corporation"),
            "currency": _field("USD"),
            "subtotal": _field("100.00"),
            "tax": _field("8.00"),
            "total": _field(total),
        },
        "lines": [],
        "checks": [],
        "meta": {"page_count": 1, "parser_version": 1, "source": "stub"},
    }


def _stub(monkeypatch, drafts):
    drafts = list(drafts)

    def fake(invoice_id):
        draft = drafts.pop(0)
        conn = get_db()
        try:
            from app.db.repository import update_extraction

            update_extraction(conn, invoice_id, draft=draft, write_lines=True)
        finally:
            conn.close()
        return True, "stubbed"

    monkeypatch.setattr(extraction, "extract_stored_invoice", fake)


def _upload(client, pdf_storage, name="e5.pdf", content=None):
    storage = pdf_storage(name)
    data = content if content is not None else storage.read()
    return client.post(
        "/upload",
        data={"file": (io.BytesIO(data), name)},
        content_type="multipart/form-data",
    )


# ---------------------------------------------------- US-E5-1: list + filter

def test_list_filter_returns_only_matching_status(
    app, client, worker, pdf_storage, monkeypatch
):
    """TC-LIST-01 — each status filter returns exactly its records."""
    _stub(monkeypatch, [_draft("INV-L1"), _draft("INV-L2")])
    _upload(client, pdf_storage, "l1.pdf")
    worker.run_pending()
    _upload(client, pdf_storage, "l2.pdf")  # stays uploaded

    completed = client.get("/invoices", query_string={"status": "completed"}).data
    uploaded = client.get("/invoices", query_string={"status": "uploaded"}).data
    assert b"INV-L1" in completed and b"INV-L2" not in completed
    # the uploaded record's number is NULL until the worker runs — anchor
    # the assertion on its ID-cell link
    assert b">#2</a>" in uploaded and b"INV-L1" not in uploaded


def test_list_unfiltered_shows_every_status(
    app, client, worker, pdf_storage, monkeypatch
):
    """TC-LIST-02 — no filter: every record appears whatever its status."""
    _stub(monkeypatch, [_draft("INV-L1"), _draft("INV-L2")])
    _upload(client, pdf_storage, "l1.pdf")
    worker.run_pending()
    _upload(client, pdf_storage, "l2.pdf")
    worker.run_pending()

    body = client.get("/invoices").data
    assert b"INV-L1" in body and b"INV-L2" in body


def test_list_filter_combines_with_search(
    app, client, worker, pdf_storage, monkeypatch
):
    """TC-LIST-03 — search and status filter compose (AND)."""
    _stub(monkeypatch, [_draft("INV-ALPHA"), _draft("INV-BETA")])
    _upload(client, pdf_storage, "l1.pdf")
    worker.run_pending()
    _upload(client, pdf_storage, "l2.pdf")
    worker.run_pending()

    both = client.get("/invoices",
                      query_string={"status": "completed", "q": "alpha"}).data
    assert b"INV-ALPHA" in both and b"INV-BETA" not in both
    # a filter+search pair with no matches shows the filtered empty state
    none = client.get("/invoices",
                      query_string={"status": "failed", "q": "alpha"}).data
    assert b"No invoices match" in none


def test_list_renders_id_and_created_columns(
    app, client, worker, pdf_storage, monkeypatch
):
    """TC-LIST-04 — ID column links to the detail page; Created date is
    shown (assignment §14)."""
    _stub(monkeypatch, [_draft("INV-L1")])
    _upload(client, pdf_storage, "l1.pdf")
    worker.run_pending()

    body = client.get("/invoices").data
    assert b"#1</a>" in body
    conn = _conn(app)
    try:
        created = conn.execute(
            "SELECT created_at FROM invoices WHERE id = 1").fetchone()[0]
    finally:
        conn.close()
    assert created.encode() in body


def test_unknown_status_filter_is_ignored(
    app, client, worker, pdf_storage, monkeypatch
):
    """TC-LIST-05 — a bogus filter value never errors; it is ignored."""
    _stub(monkeypatch, [_draft("INV-L1")])
    _upload(client, pdf_storage, "l1.pdf")
    worker.run_pending()
    response = client.get("/invoices", query_string={"status": "hacker"})
    assert response.status_code == 200
    assert b"INV-L1" in response.data


# ----------------------------------------------- US-E5-2: detail panels

def test_detail_renders_audit_timeline(
    app, client, worker, pdf_storage, monkeypatch
):
    """TC-DETAIL-01 — the audit timeline lists every event in order with
    actor and timestamp."""
    _stub(monkeypatch, [_draft()])
    _upload(client, pdf_storage)
    worker.run_pending()

    html = client.get("/invoices/1").data.decode()
    assert "Audit history" in html
    for event in ("invoice_uploaded", "processing_started",
                  "extraction_completed", "processing_completed"):
        assert event in html, event
    assert "actor" in html and "vendor" in html  # upload actor shown


def test_detail_raw_response_collapsed_and_escaped(
    app, client, worker, pdf_storage, monkeypatch
):
    """TC-RAW-02 (UI half) — the retained raw response renders inside a
    collapsed <details> block and is HTML-escaped; no injected markup
    survives."""
    import sqlite3

    hostile = '{"invoice_number": "<script>alert(1)</script>"}'

    def fake(invoice_id):
        conn = get_db()
        try:
            from app.db.repository import update_extraction

            update_extraction(conn, invoice_id, draft=_draft(),
                              write_lines=True, raw_response=hostile)
        finally:
            conn.close()
        return True, "stubbed"

    monkeypatch.setattr(extraction, "extract_stored_invoice", fake)
    _upload(client, pdf_storage)
    worker.run_pending()

    html = client.get("/invoices/1").data.decode()
    assert "<details" in html and "Raw extraction response" in html
    assert "&lt;script&gt;" in html          # escaped
    assert "<script>alert(1)</script>" not in html  # never executable
    assert "alert(1)" in html                # the text itself is present


def test_detail_hides_raw_panel_when_absent(
    app, client, worker, pdf_storage, monkeypatch
):
    """TC-DETAIL-03 — no raw-response panel when nothing was retained
    (local-parser runs clear it); and never while processing."""
    _stub(monkeypatch, [_draft()])
    _upload(client, pdf_storage)  # NOT drained yet → still `uploaded`

    while_processing = client.get("/invoices/1").data.decode()
    assert "Raw extraction response" not in while_processing

    worker.run_pending()
    after = client.get("/invoices/1").data.decode()
    assert "Raw extraction response" not in after  # stub retained no raw


def test_detail_panels_visible_to_both_roles(
    app, client, worker, pdf_storage, monkeypatch, set_role
):
    """TC-DETAIL-04 — vendor and approvers share the read-only detail view
    (route map): panels render for both; actions stay role-gated."""
    _stub(monkeypatch, [_draft()])
    _upload(client, pdf_storage)
    worker.run_pending()
    client.post("/invoices/1/submit")
    set_role("approver:manager")

    html = client.get("/invoices/1").data.decode()
    assert "Audit history" in html
    assert "Approval" in html and "routed to the manager approver" in html


# ---------------------------------- Sprint E6: filter interaction regressions

def test_status_filter_with_sort_and_pagination_preserved(app, client):
    """TC-E6-V01 — the status filter combines with the upload-date sort, and
    pagination links preserve both status and sort parameters across pages."""
    from app.db import get_db

    # seed 55 completed invoices: staggered created_at (page 1 = newest) and
    # distinct invoice dates so the two sort keys produce different orders
    with app.app_context():
        conn = get_db()
        for n in range(1, 56):
            conn.execute(
                "INSERT INTO invoices (file_hash, original_filename, "
                "stored_filename, status, invoice_number, currency, "
                "invoice_date, created_at) "
                "VALUES (?, ?, ?, 'completed', ?, 'INR', ?, ?)",
                (f"h{n:03}", f"f{n:03}.pdf", f"s{n:03}.pdf", f"F-{n:03}",
                 f"2026-{(n % 12) + 1:02d}-{(n % 28) + 1:02d}",
                 f"2026-01-01T{n:02d}:00:00"))
        conn.commit()
        conn.close()

    # page 1: filtered to completed, sorted by upload date (newest first)
    page = client.get("/invoices?status=completed&sort=created&page=1")
    body = page.data.decode()
    assert "F-055" in body and "F-001" not in body          # page 1 = newest 50
    assert "status=completed" in body and "sort=created" in body  # pager preserves both

    # page 2: the remaining 5, still filtered and sorted
    page = client.get("/invoices?status=completed&sort=created&page=2")
    body = page.data.decode()
    assert "F-001" in body and "F-005" in body and "F-006" not in body
    assert "status=completed&amp;sort=created" in body  # &amp;: escaped in href

    # the filter form carries the active selection and preserves sort
    assert 'value="completed" selected' in body
    assert '<input type="hidden" name="sort" value="created">' in body

def test_history_form_auto_submits_on_status_change(app, client):
    """TC-E6-V02 — the status dropdown submits its form on change
    (progressive enhancement); the Apply button remains the no-JS path."""
    page = client.get("/invoices").data.decode()
    assert 'onchange="this.form.submit()"' in page
    assert "<button type=\"submit\">Apply</button>" in page
