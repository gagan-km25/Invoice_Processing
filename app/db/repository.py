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
    file_type: str = "pdf",
) -> int:
    """Create a new invoice record and return its id."""
    now = _now()
    cursor = conn.execute(
        """
        INSERT INTO invoices (
            file_hash, original_filename, stored_filename, file_type,
            status, page_count, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            file_hash, original_filename, stored_filename, file_type,
            status, page_count, now, now,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_invoice(conn: sqlite3.Connection, invoice_id: int) -> sqlite3.Row | None:
    cursor = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    return cursor.fetchone()


def set_validation(
    conn: sqlite3.Connection, invoice_id: int, verdict: str, findings_json: str
) -> None:
    """Persist the business-validation verdict and findings (Sprint E3)."""
    conn.execute(
        "UPDATE invoices SET validation_status = ?, validation_json = ?, updated_at = ? WHERE id = ?",
        (verdict, findings_json, _now(), invoice_id),
    )
    conn.commit()


def set_duplicate_classification(
    conn: sqlite3.Connection, invoice_id: int, classification: str, matches_json: str
) -> None:
    """Persist the duplicate classification and match details (Sprint E3)."""
    conn.execute(
        "UPDATE invoices SET dup_status = ?, dup_matches = ?, updated_at = ? WHERE id = ?",
        (classification, matches_json, _now(), invoice_id),
    )
    conn.commit()


def find_duplicate_candidates(
    conn: sqlite3.Connection, invoice_id: int
) -> list[sqlite3.Row]:
    """Other invoices in duplicate-comparable states, excluding self.
    (The v2-only `saved` alias left the candidate list with the v3
    tightening — no row can carry it any more.)"""
    placeholders = ", ".join("?" for _ in (
        "completed", "validation_failed", "pending_approval",
        "approved", "rejected",
    ))
    return conn.execute(
        f"SELECT id, vendor, invoice_number, invoice_date, total "
        f"FROM invoices WHERE id != ? AND status IN ({placeholders}) "
        "AND vendor IS NOT NULL AND invoice_number IS NOT NULL ORDER BY id",
        (invoice_id,
         "completed", "validation_failed", "pending_approval",
         "approved", "rejected"),
    ).fetchall()


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


def find_duplicate_records(
    conn: sqlite3.Connection,
    vendor: str,
    invoice_number: str,
    exclude_id: int | None = None,
) -> list[sqlite3.Row]:
    """Records matching vendor + invoice number, case-insensitively, in ANY
    status (Sprint E5 rewire of US-S3-06: with `saved` removed from the
    lifecycle, the save-time duplicate gate compares against every stored
    record). The invoice being saved is always excluded."""
    sql = (
        "SELECT * FROM invoices WHERE "
        "vendor = ? COLLATE NOCASE AND invoice_number = ? COLLATE NOCASE"
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


def list_invoices(
    conn: sqlite3.Connection,
    *,
    status: str | None = None,
    q: str | None = None,
    order: str = "invoice_date",
    limit: int = 50,
    offset: int = 0,
) -> list[sqlite3.Row]:
    """All invoices for the history/list page (Sprint E5, assignment §14):
    descending by the chosen sort key with id as tiebreak (undated rows
    last), optional exact-status filter and search fragment, minimal
    pagination. `order` is whitelisted: 'invoice_date' (default) or
    'created_at' (upload/creation timestamp); anything else falls back to
    'invoice_date'."""
    if order not in ("invoice_date", "created_at"):
        order = "invoice_date"
    fragment, params = _search_filter(q)
    status_clause = ""
    if status:
        # status placeholder precedes the search fragment in the SQL
        params = [status, *params]
        status_clause = " AND status = ?"
    sql = (
        f"SELECT * FROM invoices WHERE 1 = 1{status_clause}{fragment} "
        f"ORDER BY {order} DESC, id DESC LIMIT ? OFFSET ?"
    )
    return conn.execute(sql, [*params, limit, offset]).fetchall()


def count_invoices(
    conn: sqlite3.Connection,
    *,
    status: str | None = None,
    q: str | None = None,
) -> int:
    """Total invoices matching the same filter as list_invoices."""
    fragment, params = _search_filter(q)
    status_clause = ""
    if status:
        params = [status, *params]
        status_clause = " AND status = ?"
    return conn.execute(
        f"SELECT COUNT(*) FROM invoices WHERE 1 = 1{status_clause}{fragment}",
        params,
    ).fetchone()[0]


def get_lines(conn: sqlite3.Connection, invoice_id: int) -> list[sqlite3.Row]:
    """Line items of one invoice, in line-number order."""
    return conn.execute(
        "SELECT * FROM invoice_lines WHERE invoice_id = ? ORDER BY line_number",
        (invoice_id,),
    ).fetchall()


def delete_invoice(conn: sqlite3.Connection, invoice_id: int) -> None:
    """Delete an invoice; line items and audit rows are removed by the FK
    cascade (PRAGMA foreign_keys = ON is set by get_db). Guard (Sprint E5,
    approved decision 1): records still `uploaded` or `processing` may not
    be deleted — a queued job owns the former, the pipeline owns the
    latter; every other status is deletable with confirmation."""
    record = get_invoice(conn, invoice_id)
    if record is None:
        raise ValueError(f"invoice {invoice_id} not found")
    if record["status"] in ("uploaded", "processing"):
        raise ValueError(
            f"invoice {invoice_id} is {record['status']!r} — it cannot be "
            "deleted while queued or processing"
        )
    conn.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
    conn.commit()


def submit_for_approval(
    conn: sqlite3.Connection,
    invoice_id: int,
    *,
    approver_role: str,
    actor: str = "vendor",
) -> None:
    """Transition a submittable invoice → `pending_approval` in ONE
    transaction (Sprint E4, assignment §10): status + `approver_role` +
    the `review_submitted` and `approval_assigned` audit entries — the
    routing decision is never separated from the status change.

    Eligibility here is defense in depth (the workflow authority is
    `workflow.transition_target`, checked by the caller; this module
    cannot import workflow without a cycle). Only `completed` and
    `validation_failed` are submittable (approved decision 3: `saved`
    stays outside the approval flow). Raises ValueError for a missing
    record or an ineligible status.
    """
    record = get_invoice(conn, invoice_id)
    if record is None:
        raise ValueError(f"invoice {invoice_id} not found")
    if record["status"] not in ("completed", "validation_failed"):
        raise ValueError(
            f"invoice {invoice_id} is {record['status']!r}, not submittable"
        )
    now = _now()
    try:
        conn.execute(
            "UPDATE invoices SET status = 'pending_approval', "
            "approver_role = ?, updated_at = ? WHERE id = ?",
            (approver_role, now, invoice_id),
        )
        conn.execute(
            "INSERT INTO invoice_audit (invoice_id, event_type, actor, details, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (invoice_id, "review_submitted", actor, "submitted for approval", now),
        )
        conn.execute(
            "INSERT INTO invoice_audit (invoice_id, event_type, actor, details, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                invoice_id,
                "approval_assigned",
                "system",
                f"routed to the {approver_role} approver",
                now,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def record_approval_decision(
    conn: sqlite3.Connection,
    invoice_id: int,
    *,
    decision: str,
    actor: str,
    rejection_reason: str | None = None,
) -> None:
    """Apply an approver's decision in ONE transaction (Sprint E4,
    assignment §11): `pending_approval` → approved/rejected, the decision
    columns (`acted_by`, `acted_at`, and `rejection_reason` on reject) and
    the matching audit entry together. `decision` is `approve` or `reject`;
    legality is checked by the caller via the workflow authority and
    defensively here. Raises ValueError for a missing record, an
    ineligible status, or an unknown decision."""
    record = get_invoice(conn, invoice_id)
    if record is None:
        raise ValueError(f"invoice {invoice_id} not found")
    if record["status"] != "pending_approval":
        raise ValueError(
            f"invoice {invoice_id} is {record['status']!r}, not "
            "pending_approval — it cannot be approved or rejected"
        )
    if decision == "approve":
        new_status, event = "approved", "invoice_approved"
    elif decision == "reject":
        new_status, event = "rejected", "invoice_rejected"
    else:
        raise ValueError(f"unknown decision {decision!r}")
    now = _now()
    try:
        assignments = [
            "status = ?", "acted_by = ?", "acted_at = ?", "updated_at = ?"
        ]
        params: list = [new_status, actor, now, now]
        if decision == "reject":
            assignments.append("rejection_reason = ?")
            params.append(rejection_reason)
        params.append(invoice_id)
        conn.execute(
            f"UPDATE invoices SET {', '.join(assignments)} WHERE id = ?",
            params,
        )
        conn.execute(
            "INSERT INTO invoice_audit (invoice_id, event_type, actor, details, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (invoice_id, event, actor, rejection_reason, now),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def list_pending_for_role(
    conn: sqlite3.Connection, approver_role: str
) -> list[sqlite3.Row]:
    """The approval queue for one routing role: pending invoices routed to
    it, most recently submitted first (Sprint E4, ARCHITECTURE §6)."""
    return conn.execute(
        "SELECT * FROM invoices WHERE status = 'pending_approval' "
        "AND approver_role = ? ORDER BY updated_at DESC, id DESC",
        (approver_role,),
    ).fetchall()


def save_invoice(
    conn: sqlite3.Connection,
    invoice_id: int,
    *,
    header: dict,
    lines: list[dict],
) -> None:
    """Persist a reviewed invoice's confirmed values atomically (US-S3-05,
    rewired Sprint E5): the record KEEPS its lifecycle status (`completed`
    for pipeline output, legacy `extracted` rows until the v3 migration) —
    the `saved` transitional status is gone, and approval runs from
    `completed`/`validation_failed` per the E4 workflow.

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
                bill_to_address = ?, ship_to_name = ?, ship_to_address = ?,
                po_number = ?,
                subtotal = ?, discount = ?, tax = ?, tax_rate = ?, total = ?,
                updated_at = ?
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
                header.get("bill_to_address"),
                header.get("ship_to_name"),
                header.get("ship_to_address"),
                header.get("po_number"),
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
                    unit_price, amount, line_tax
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    invoice_id,
                    line.get("line_number"),
                    line.get("description"),
                    _to_real(line.get("quantity")),
                    _to_real(line.get("unit_price")),
                    _to_real(line.get("amount")),
                    _to_real(line.get("tax")),
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
    raw_response: str | None = None,
) -> None:
    """Move an invoice to `new_status` and write the audit entry in ONE
    transaction (approved plan §C: the lifecycle event is never separated
    from the status change). `error_message` optionally records the
    user-safe failure reason and `raw_response` the size-capped provider
    response in the same transaction (terminal failures). Transition
    legality is enforced by app/services/workflow.py — this function only
    performs an already-validated change and refuses unknown invoices."""
    record = get_invoice(conn, invoice_id)
    if record is None:
        raise ValueError(f"invoice {invoice_id} not found")
    now = _now()
    try:
        assignments = ["status = ?", "updated_at = ?"]
        params: list = [new_status, now]
        if error_message is not None:
            assignments.append("error_message = ?")
            params.append(error_message)
        if raw_response is not None:
            assignments.append("raw_response = ?")
            params.append(raw_response)
        params.append(invoice_id)
        conn.execute(
            f"UPDATE invoices SET {', '.join(assignments)} WHERE id = ?",
            params,
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
    raw_response: str | None = None,
    clear_raw_response: bool = False,
) -> None:
    """Persist extraction output: header columns, line items, draft JSON.

    Sprint E1: `status` is optional — None leaves `invoices.status`
    untouched (the pipeline owns status via workflow transitions). Line
    items are replaced when `write_lines` is true (idempotent
    re-extraction). `raw_response` (when given) stores the size-capped AI
    response; `clear_raw_response=True` empties it (local-parser runs).
    The whole thing runs in one transaction — the record is never
    half-written (NFR-5).
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
        "bill_to_address = ?", "ship_to_name = ?", "ship_to_address = ?",
        "po_number = ?",
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
        column_value(fields.get("bill_to_address")),
        column_value(fields.get("ship_to_name")),
        column_value(fields.get("ship_to_address")),
        column_value(fields.get("po_number")),
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
        # Insert before the trailing `updated_at` assignment/param.
        index = len(assignments) - 1
        assignments.insert(index, "status = ?")
        params.insert(index, status)
    if raw_response is not None:
        assignments.append("raw_response = ?")
        params.append(raw_response)
    if clear_raw_response:
        assignments.append("raw_response = NULL")
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
                    unit_price, amount, line_tax
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    invoice_id,
                    item.get("line_number"),
                    item.get("description"),
                    float(item["quantity"]) if item.get("quantity") is not None else None,
                    float(item["unit_price"]) if item.get("unit_price") is not None else None,
                    float(item["amount"]) if item.get("amount") is not None else None,
                    float(item["tax"]) if item.get("tax") is not None else None,
                ),
            )
    conn.commit()
