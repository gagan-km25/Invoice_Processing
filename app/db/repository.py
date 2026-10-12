"""All SQL lives here (architecture rule: nothing else writes SQL).

Parameterized statements only — no string-built SQL (requirements §10.8).
Money note: this module never does money math; monetary values are stored
as REAL and handled as decimal.Decimal at service boundaries (M-3).
"""
import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _to_real(value):
    """Decimal → float for REAL storage; None passes through (M-3 boundary)."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return value


def insert_invoice(
    conn: sqlite3.Connection,
    *,
    file_hash: str,
    original_filename: str,
    stored_filename: str,
    status: str,
    page_count: int | None = None,
) -> int:
    """Create a new invoice record and return its id."""
    now = _now()
    cursor = conn.execute(
        """
        INSERT INTO invoices (
            file_hash, original_filename, stored_filename,
            status, page_count, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (file_hash, original_filename, stored_filename, status, page_count, now, now),
    )
    conn.commit()
    return cursor.lastrowid


def get_invoice(conn: sqlite3.Connection, invoice_id: int) -> sqlite3.Row | None:
    cursor = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    return cursor.fetchone()


def find_by_hash(
    conn: sqlite3.Connection, file_hash: str, exclude_id: int | None = None
) -> list[sqlite3.Row]:
    """Records with the same file content (duplicate warning, FR-15)."""
    if exclude_id is None:
        cursor = conn.execute(
            "SELECT * FROM invoices WHERE file_hash = ? ORDER BY id", (file_hash,)
        )
    else:
        cursor = conn.execute(
            "SELECT * FROM invoices WHERE file_hash = ? AND id != ? ORDER BY id",
            (file_hash, exclude_id),
        )
    return cursor.fetchall()


def list_recent(conn: sqlite3.Connection, limit: int = 10) -> list[sqlite3.Row]:
    """Newest records first, for the home-page panel (AC-5.1 arrives in S4)."""
    cursor = conn.execute(
        "SELECT * FROM invoices ORDER BY id DESC LIMIT ?", (limit,)
    )
    return cursor.fetchall()


def find_saved_duplicates(
    conn: sqlite3.Connection,
    vendor: str,
    invoice_number: str,
    exclude_id: int | None = None,
) -> list[sqlite3.Row]:
    """Saved records matching vendor + invoice number, case-insensitively
    (US-S3-06). Drafts (uploaded/extracted/failed) never count as duplicates."""
    sql = (
        "SELECT * FROM invoices WHERE status = 'saved' "
        "AND vendor = ? COLLATE NOCASE AND invoice_number = ? COLLATE NOCASE"
    )
    params: list = [vendor, invoice_number]
    if exclude_id is not None:
        sql += " AND id != ?"
        params.append(exclude_id)
    return conn.execute(sql + " ORDER BY id", params).fetchall()


def _search_filter(q: str | None) -> tuple[str, list]:
    """Optional search fragment for history: substring match on invoice number
    or vendor, case-insensitive, user %/_ treated as literal characters
    (escaped, declared via ESCAPE — TC-S4-U06/I18)."""
    if not q:
        return "", []
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    return (
        " AND (invoice_number LIKE ? ESCAPE '\\' OR vendor LIKE ? ESCAPE '\\')",
        [pattern, pattern],
    )


def list_saved(
    conn: sqlite3.Connection,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[sqlite3.Row]:
    """Saved invoices for the history page: newest invoice date first (id as
    tiebreak), optional search, minimal pagination (docs/09 §4)."""
    fragment, params = _search_filter(q)
    sql = (
        f"SELECT * FROM invoices WHERE status = 'saved'{fragment} "
        "ORDER BY invoice_date DESC, id DESC LIMIT ? OFFSET ?"
    )
    return conn.execute(sql, [*params, limit, offset]).fetchall()


def count_saved(conn: sqlite3.Connection, q: str | None = None) -> int:
    """Total saved invoices matching the same filter as list_saved."""
    fragment, params = _search_filter(q)
    return conn.execute(
        f"SELECT COUNT(*) FROM invoices WHERE status = 'saved'{fragment}", params
    ).fetchone()[0]


def get_lines(conn: sqlite3.Connection, invoice_id: int) -> list[sqlite3.Row]:
    """Line items of one invoice, in line-number order."""
    return conn.execute(
        "SELECT * FROM invoice_lines WHERE invoice_id = ? ORDER BY line_number",
        (invoice_id,),
    ).fetchall()


def delete_invoice(conn: sqlite3.Connection, invoice_id: int) -> None:
    """Delete a saved invoice; line items are removed by the FK cascade
    (PRAGMA foreign_keys = ON is set by get_db). Guard: only `saved` records
    may be deleted here (US-S4-05/06)."""
    record = get_invoice(conn, invoice_id)
    if record is None:
        raise ValueError(f"invoice {invoice_id} not found")
    if record["status"] != "saved":
        raise ValueError(
            f"invoice {invoice_id} is {record['status']!r}, not 'saved'"
        )
    conn.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
    conn.commit()


def save_invoice(
    conn: sqlite3.Connection,
    invoice_id: int,
    *,
    header: dict,
    lines: list[dict],
) -> None:
    """Transition a reviewed invoice → `saved` atomically (US-S3-05).

    Sprint E1: eligible source statuses are `extracted` (legacy rows) and
    `completed` (the pipeline's extraction-complete state); the record is
    written as `saved`, the human-flow terminal state until Sprint E4
    introduces submit-for-approval.

    Writes the reviewed header columns and replaces the full line set in ONE
    transaction. Any failure rolls everything back and re-raises — the record
    is left exactly as it was (header and prior lines). Raises ValueError for
    missing records or an ineligible status (double-submit guard, AC-05.3).
    `extraction_json` is intentionally untouched (AC-05.4).
    """
    record = get_invoice(conn, invoice_id)
    if record is None:
        raise ValueError(f"invoice {invoice_id} not found")
    if record["status"] not in ("extracted", "completed"):
        raise ValueError(
            f"invoice {invoice_id} is {record['status']!r}, not reviewable"
        )
    try:
        conn.execute(
            """
            UPDATE invoices SET
                vendor = ?, vendor_tax_id = ?, invoice_number = ?,
                invoice_date = ?, due_date = ?, bill_to = ?, currency = ?,
                subtotal = ?, discount = ?, tax = ?, tax_rate = ?, total = ?,
                status = 'saved', updated_at = ?
            WHERE id = ?
            """,
            (
                header.get("vendor"),
                header.get("vendor_tax_id"),
                header.get("invoice_number"),
                header.get("invoice_date"),
                header.get("due_date"),
                header.get("bill_to"),
                header.get("currency"),
                _to_real(header.get("subtotal")),
                _to_real(header.get("discount")),
                _to_real(header.get("tax")),
                _to_real(header.get("tax_rate")),
                _to_real(header.get("total")),
                _now(),
                invoice_id,
            ),
        )
        conn.execute(
            "DELETE FROM invoice_lines WHERE invoice_id = ?", (invoice_id,)
        )
        for line in lines:
            conn.execute(
                """
                INSERT INTO invoice_lines (
                    invoice_id, line_number, description, quantity,
                    unit_price, amount
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    invoice_id,
                    line.get("line_number"),
                    line.get("description"),
                    _to_real(line.get("quantity")),
                    _to_real(line.get("unit_price")),
                    _to_real(line.get("amount")),
                ),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def insert_audit(
    conn: sqlite3.Connection,
    invoice_id: int,
    event_type: str,
    actor: str = "system",
    details: str | None = None,
) -> int:
    """Append one audit entry; returns the audit row id."""
    cursor = conn.execute(
        """
        INSERT INTO invoice_audit (invoice_id, event_type, actor, details, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (invoice_id, event_type, actor, details, _now()),
    )
    conn.commit()
    return cursor.lastrowid


def get_audit(
    conn: sqlite3.Connection, invoice_id: int
) -> list[sqlite3.Row]:
    """Audit entries of one invoice, oldest first."""
    return conn.execute(
        "SELECT * FROM invoice_audit WHERE invoice_id = ? ORDER BY id",
        (invoice_id,),
    ).fetchall()


def transition_status(
    conn: sqlite3.Connection,
    invoice_id: int,
    *,
    new_status: str,
    event_type: str,
    actor: str = "system",
    details: str | None = None,
    error_message: str | None = None,
) -> None:
    """Move an invoice to `new_status` and write the audit entry in ONE
    transaction (approved plan §C: the lifecycle event is never separated
    from the status change). `error_message` optionally records the
    user-safe failure reason in the same transaction (terminal failures).
    Transition legality is enforced by app/services/workflow.py — this
    function only performs an already-validated change and refuses unknown
    invoices."""
    record = get_invoice(conn, invoice_id)
    if record is None:
        raise ValueError(f"invoice {invoice_id} not found")
    now = _now()
    try:
        if error_message is None:
            conn.execute(
                "UPDATE invoices SET status = ?, updated_at = ? WHERE id = ?",
                (new_status, now, invoice_id),
            )
        else:
            conn.execute(
                "UPDATE invoices SET status = ?, updated_at = ?, "
                "error_message = ? WHERE id = ?",
                (new_status, now, error_message, invoice_id),
            )
        conn.execute(
            """
            INSERT INTO invoice_audit (invoice_id, event_type, actor, details, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (invoice_id, event_type, actor, details, now),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def set_extract_attempts(conn: sqlite3.Connection, invoice_id: int, attempts: int) -> None:
    """Persist the pipeline's attempt counter (visible, survives restarts)."""
    conn.execute(
        "UPDATE invoices SET extract_attempts = ?, updated_at = ? WHERE id = ?",
        (attempts, _now(), invoice_id),
    )
    conn.commit()


def update_extraction(
    conn: sqlite3.Connection,
    invoice_id: int,
    *,
    draft: dict,
    status: str | None = None,
    error_message: str | None = None,
    write_lines: bool = True,
) -> None:
    """Persist extraction output: header columns, line items, draft JSON.

    Sprint E1: `status` is now optional — None leaves `invoices.status`
    untouched (the pipeline owns status via workflow transitions). Line
    items are replaced when `write_lines` is true (idempotent
    re-extraction). The whole thing runs in one transaction — the record is
    never half-written (NFR-5).
    """
    from decimal import Decimal  # local import keeps repository dependency-light

    def column_value(field: dict | None):
        if not field or field.get("status") == "missing":
            return None
        value = field.get("value")
        return float(value) if isinstance(value, Decimal) else value

    fields = draft.get("fields", {})
    now = _now()
    assignments = [
        "vendor = ?", "vendor_tax_id = ?", "invoice_number = ?",
        "invoice_date = ?", "due_date = ?", "bill_to = ?", "currency = ?",
        "subtotal = ?", "discount = ?", "tax_rate = ?", "tax = ?", "total = ?",
        "page_count = ?", "extraction_json = ?", "updated_at = ?",
    ]
    params: list = [
        column_value(fields.get("vendor")),
        column_value(fields.get("vendor_tax_id")),
        column_value(fields.get("invoice_number")),
        column_value(fields.get("invoice_date")),
        column_value(fields.get("due_date")),
        column_value(fields.get("bill_to")),
        column_value(fields.get("currency")),
        column_value(fields.get("subtotal")),
        column_value(fields.get("discount")),
        column_value(fields.get("tax_rate")),
        column_value(fields.get("tax")),
        column_value(fields.get("total")),
        (draft.get("meta") or {}).get("page_count"),
        json.dumps(draft, ensure_ascii=False, default=str),
        now,
    ]
    if status is not None:
        assignments.insert(14, "status = ?")
        params.insert(14, status)
    if error_message is not None:
        assignments.append("error_message = ?")
        params.append(error_message)
    params.append(invoice_id)
    conn.execute(
        f"UPDATE invoices SET {', '.join(assignments)} WHERE id = ?",
        params,
    )
    if write_lines:
        conn.execute("DELETE FROM invoice_lines WHERE invoice_id = ?", (invoice_id,))
        for item in draft.get("lines", []):
            conn.execute(
                """
                INSERT INTO invoice_lines (
                    invoice_id, line_number, description, quantity,
                    unit_price, amount
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    invoice_id,
                    item.get("line_number"),
                    item.get("description"),
                    float(item["quantity"]) if item.get("quantity") is not None else None,
                    float(item["unit_price"]) if item.get("unit_price") is not None else None,
                    float(item["amount"]) if item.get("amount") is not None else None,
                ),
            )
    conn.commit()
