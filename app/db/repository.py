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


def save_invoice(
    conn: sqlite3.Connection,
    invoice_id: int,
    *,
    header: dict,
    lines: list[dict],
) -> None:
    """Transition `extracted` → `saved` atomically (US-S3-05).

    Writes the reviewed header columns and replaces the full line set in ONE
    transaction. Any failure rolls everything back and re-raises — the record
    is left exactly as it was (header and prior lines). Raises ValueError for
    missing records or a status other than `extracted` (double-submit guard,
    AC-05.3). `extraction_json` is intentionally untouched (AC-05.4).
    """
    record = get_invoice(conn, invoice_id)
    if record is None:
        raise ValueError(f"invoice {invoice_id} not found")
    if record["status"] != "extracted":
        raise ValueError(
            f"invoice {invoice_id} is {record['status']!r}, not 'extracted'"
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


def update_extraction(
    conn: sqlite3.Connection,
    invoice_id: int,
    *,
    draft: dict,
    status: str,
    error_message: str | None = None,
) -> None:
    """Persist extraction output: header columns, line items, draft JSON.

    `draft["fields"]` values are written only when found/ambiguous; missing
    stays NULL. Line items are replaced (idempotent re-extraction). The whole
    thing runs in one transaction — the record is never half-written (NFR-5).
    """
    from decimal import Decimal  # local import keeps repository dependency-light

    def column_value(field: dict | None):
        if not field or field.get("status") == "missing":
            return None
        value = field.get("value")
        return float(value) if isinstance(value, Decimal) else value

    fields = draft.get("fields", {})
    now = _now()
    conn.execute(
        """
        UPDATE invoices SET
            vendor = ?, vendor_tax_id = ?, invoice_number = ?,
            invoice_date = ?, due_date = ?, bill_to = ?, currency = ?,
            subtotal = ?, discount = ?, tax_rate = ?, tax = ?, total = ?,
            page_count = ?, extraction_json = ?,
            status = ?, error_message = ?, updated_at = ?
        WHERE id = ?
        """,
        (
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
            status,
            error_message,
            now,
            invoice_id,
        ),
    )
    if status == "extracted":
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
