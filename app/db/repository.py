"""All SQL lives here (architecture rule: nothing else writes SQL).

Parameterized statements only — no string-built SQL (requirements §10.8).
Money note: this module never does money math; monetary values are stored
as REAL and handled as decimal.Decimal at service boundaries (M-3).
"""
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
