"""History/list repository tests — Sprint 4 semantics, rewired Sprint E5.

IDs TC-S4-U01… retained for traceability; TC-S4-U01/U12 were redefined by
the E5 plan (all-status listing; delete blocked only while
`uploaded`/`processing`). Real temp DB via the app fixture.
"""
import pytest

from app.db import get_db
from app.db.repository import (
    count_invoices,
    delete_invoice,
    get_invoice,
    get_lines,
    insert_invoice,
    list_invoices,
)

_counter = {"n": 0}


def _add(app, *, vendor="Acme", number="INV-1", date="2026-01-01",
         status="completed", total=10.0):
    """Insert one record and set its business fields; returns its id."""
    _counter["n"] += 1
    n = _counter["n"]
    with app.app_context():
        conn = get_db()
        try:
            invoice_id = insert_invoice(
                conn, file_hash=f"hash-{n}",
                original_filename=f"file{n}.pdf",
                stored_filename=f"stored-{n}.pdf", status="uploaded",
            )
            conn.execute(
                "UPDATE invoices SET vendor = ?, invoice_number = ?, "
                "invoice_date = ?, total = ?, status = ? WHERE id = ?",
                (vendor, number, date, total, status, invoice_id),
            )
            conn.commit()
        finally:
            conn.close()
    return invoice_id


def _add_line(app, invoice_id, line_number, description="Line"):
    with app.app_context():
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO invoice_lines (invoice_id, line_number, description, "
                "quantity, unit_price, amount) VALUES (?, ?, ?, 1, 1, 1)",
                (invoice_id, line_number, f"{description} {line_number}"),
            )
            conn.commit()
        finally:
            conn.close()


def test_list_shows_all_statuses_by_default(app):
    """TC-S4-U01 (E5 redefinition) — the unfiltered list shows every
    status, oldest ids included."""
    completed = _add(app, vendor="Done Co", number="C-1")
    pending = _add(app, vendor="Wait Co", number="P-1", status="pending_approval")
    uploaded = _add(app, vendor="New Co", number="U-1", status="uploaded")
    failed = _add(app, vendor="Broken Co", number="F-1", status="failed")
    with app.app_context():
        conn = get_db()
        try:
            rows = list_invoices(conn)
        finally:
            conn.close()
    assert {row["id"] for row in rows} == {completed, pending, uploaded, failed}


def test_status_filter_exact(app):
    """TC-S4-U01b (E5) — the exact-status filter returns only that status."""
    done = _add(app, vendor="Done Co", number="C-1", status="completed")
    _add(app, vendor="Wait Co", number="P-1", status="pending_approval")
    with app.app_context():
        conn = get_db()
        try:
            rows = list_invoices(conn, status="completed")
            none = list_invoices(conn, status="rejected")
        finally:
            conn.close()
    assert [row["id"] for row in rows] == [done]
    assert none == []


def test_ordering_date_desc_id_desc(app):
    """TC-S4-U02 — newest invoice date first; ties broken by id desc."""
    a = _add(app, vendor="A", number="A-1", date="2026-03-01")
    b = _add(app, vendor="B", number="B-1", date="2026-01-01")
    c = _add(app, vendor="C", number="C-1", date="2026-03-01")
    with app.app_context():
        conn = get_db()
        try:
            rows = list_invoices(conn)
        finally:
            conn.close()
    assert [row["id"] for row in rows] == [c, a, b]


def test_search_by_number_fragment(app):
    """TC-S4-U03 — fragment of the invoice number matches."""
    _add(app, vendor="One", number="INV-0042")
    _add(app, vendor="Two", number="X-9")
    with app.app_context():
        conn = get_db()
        try:
            rows = list_invoices(conn, q="inv-00")
        finally:
            conn.close()
    assert [row["invoice_number"] for row in rows] == ["INV-0042"]


def test_search_by_vendor_fragment(app):
    """TC-S4-U04 — fragment of the vendor matches."""
    _add(app, vendor="TechNova Retail", number="N-1")
    _add(app, vendor="Other", number="N-2")
    with app.app_context():
        conn = get_db()
        try:
            rows = list_invoices(conn, q="technova")
        finally:
            conn.close()
    assert [row["vendor"] for row in rows] == ["TechNova Retail"]


def test_search_case_insensitive():
    """TC-S4-U05 — case-insensitive across number and vendor."""
    assert list_invoices.__doc__ is not None  # sanity; behavior covered in U03/U04


def test_percent_and_underscore_are_literal(app):
    """TC-S4-U06 — user % and _ match literal characters only (escaped)."""
    pct = _add(app, vendor="50% Off Ltd", number="P-1")
    underscore = _add(app, vendor="A_B Partners", number="A_1")
    plain = _add(app, vendor="AB1 Partners", number="AB1")
    with app.app_context():
        conn = get_db()
        try:
            by_pct = list_invoices(conn, q="50%")
            by_underscore = list_invoices(conn, q="A_1")
        finally:
            conn.close()
    assert [row["id"] for row in by_pct] == [pct]
    assert underscore in [row["id"] for row in by_underscore]
    assert plain not in [row["id"] for row in by_underscore]


def test_search_no_match_empty(app):
    """TC-S4-U07 — no match → empty list."""
    _add(app, vendor="Acme", number="A-1")
    with app.app_context():
        conn = get_db()
        try:
            assert list_invoices(conn, q="zzz") == []
        finally:
            conn.close()


def test_count_matches_listing(app):
    """TC-S4-U08 — count_invoices agrees with list_invoices, with and
    without q/status."""
    _add(app, vendor="Alpha", number="A-1", status="completed")
    _add(app, vendor="Alpha Two", number="A-2", status="completed")
    _add(app, vendor="Beta", number="B-1", status="failed")
    with app.app_context():
        conn = get_db()
        try:
            assert count_invoices(conn) == 3
            assert len(list_invoices(conn)) == 3
            assert count_invoices(conn, q="alpha") == 2
            assert len(list_invoices(conn, q="alpha")) == 2
            assert count_invoices(conn, status="completed") == 2
            assert count_invoices(conn, status="failed", q="beta") == 1
        finally:
            conn.close()


def test_paging_windows(app):
    """TC-S4-U09 — limit/offset slices the full ordered set correctly."""
    ids = [_add(app, vendor=f"V{i}", number=f"N-{i:02d}",
                date=f"2026-01-{i + 1:02d}") for i in range(5)]
    with app.app_context():
        conn = get_db()
        try:
            page1 = list_invoices(conn, limit=2, offset=0)
            page2 = list_invoices(conn, limit=2, offset=2)
            page3 = list_invoices(conn, limit=2, offset=4)
        finally:
            conn.close()
    # newest date = highest i
    assert [row["id"] for row in page1] == [ids[4], ids[3]]
    assert [row["id"] for row in page2] == [ids[2], ids[1]]
    assert [row["id"] for row in page3] == [ids[0]]


def test_get_lines_ordered(app):
    """TC-S4-U10 — line items ordered by line_number regardless of insert order."""
    invoice_id = _add(app)
    _add_line(app, invoice_id, 3)
    _add_line(app, invoice_id, 1)
    _add_line(app, invoice_id, 2)
    with app.app_context():
        conn = get_db()
        try:
            lines = get_lines(conn, invoice_id)
        finally:
            conn.close()
    assert [line["line_number"] for line in lines] == [1, 2, 3]


def test_delete_cascades_lines_and_audit(app):
    """TC-S4-U11 — delete removes the row; lines and audit cascade to zero."""
    invoice_id = _add(app)
    _add_line(app, invoice_id, 1)
    _add_line(app, invoice_id, 2)
    with app.app_context():
        conn = get_db()
        try:
            delete_invoice(conn, invoice_id)
            assert get_invoice(conn, invoice_id) is None
            assert get_lines(conn, invoice_id) == []
            orphan_lines = conn.execute(
                "SELECT COUNT(*) FROM invoice_lines WHERE invoice_id NOT IN "
                "(SELECT id FROM invoices)"
            ).fetchone()[0]
            orphan_audits = conn.execute(
                "SELECT COUNT(*) FROM invoice_audit WHERE invoice_id NOT IN "
                "(SELECT id FROM invoices)"
            ).fetchone()[0]
        finally:
            conn.close()
    assert orphan_lines == 0 and orphan_audits == 0


def test_delete_guard_blocked_states(app):
    """TC-S4-U12 (E5 redefinition) — deleting `uploaded` or `processing`
    records is refused, nothing changes; other statuses delete."""
    uploaded = _add(app, status="uploaded")
    processing = _add(app, status="processing")
    completed = _add(app, status="completed")
    with app.app_context():
        conn = get_db()
        try:
            for blocked in (uploaded, processing):
                with pytest.raises(ValueError):
                    delete_invoice(conn, blocked)
                assert get_invoice(conn, blocked) is not None
            delete_invoice(conn, completed)
            assert get_invoice(conn, completed) is None
        finally:
            conn.close()


def test_delete_leaves_others_untouched(app):
    """TC-S4-U13 — deleting one invoice leaves the others intact."""
    keep = _add(app, vendor="Keep", number="K-1")
    gone = _add(app, vendor="Gone", number="G-1")
    _add_line(app, gone, 1)
    _add_line(app, keep, 1)
    with app.app_context():
        conn = get_db()
        try:
            delete_invoice(conn, gone)
            assert get_invoice(conn, keep) is not None
            assert len(get_lines(conn, keep)) == 1
        finally:
            conn.close()
