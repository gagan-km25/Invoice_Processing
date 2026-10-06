"""All SQL lives here (architecture rule: nothing else writes SQL).

Parameterized statements only — no string-built SQL (requirements §10.8).
Money note: this module never does money math; monetary values are stored
as REAL and handled as decimal.Decimal at service boundaries (M-3).
"""
import json
import sqlite3
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
