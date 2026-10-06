"""Invoice review & save routes (Sprint 3). Thin HTTP layer:
validation/merge lives in services/review.py, the transaction in the
repository. Guards: 404 for unknown ids; only `extracted` records can be
reviewed or saved; duplicates require explicit confirmation (US-S3-06).
"""
import json

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)

from app.db import get_db
from app.db.repository import (
    count_saved,
    find_by_hash,
    find_saved_duplicates,
    get_invoice,
    get_lines,
    list_saved,
    save_invoice,
)
from app.services.invoices import delete_saved_invoice
from app.services.review import (
    form_to_view,
    prefill_from_draft,
    validate_and_merge,
    with_blank_rows,
)

bp = Blueprint("invoices", __name__)

PAGE_SIZE = 50  # minimal pagination, docs/09 §4


def _flags_of(record) -> dict:
    """Normalized per-field extraction statuses for flag badges."""
    return {
        name: (field.get("status", "missing") if isinstance(field, dict) else "missing")
        for name, field in (_draft_of(record).get("fields", {})).items()
    }


def _load(invoice_id: int):
    conn = get_db()
    try:
        return get_invoice(conn, invoice_id)
    finally:
        conn.close()


def _draft_of(record) -> dict:
    if not record["extraction_json"]:
        return {"fields": {}, "lines": []}
    return json.loads(record["extraction_json"])


def _saved_hash_duplicates(record) -> list:
    conn = get_db()
    try:
        duplicates = [
            row
            for row in find_by_hash(conn, record["file_hash"], exclude_id=record["id"])
            if row["status"] == "saved"
        ]
    finally:
        conn.close()
    return duplicates


@bp.get("/invoices/<int:invoice_id>/review")
def review(invoice_id: int):
    record = _load(invoice_id)
    if record is None:
        abort(404)
    if record["status"] != "extracted":
        flash(
            f"Record #{invoice_id} is {record['status']} — only extracted "
            "records can be reviewed.",
            "warning",
        )
        return redirect(url_for("uploads.index"))
    values, line_rows, flags = prefill_from_draft(_draft_of(record))
    return render_template(
        "review.html",
        invoice=record,
        values=values,
        line_rows=with_blank_rows(line_rows),
        flags=flags,
        errors={},
        warnings=[],
        dup_ids=[],
    )


@bp.post("/invoices/<int:invoice_id>/save")
def save(invoice_id: int):
    record = _load(invoice_id)
    if record is None:
        abort(404)
    if record["status"] != "extracted":
        flash(
            f"Record #{invoice_id} is {record['status']} and cannot be saved "
            "again.",
            "warning",
        )
        return redirect(url_for("uploads.index"))

    result = validate_and_merge(request.form)
    if not result["ok"]:
        values, line_rows = form_to_view(request.form)
        return render_template(
            "review.html",
            invoice=record,
            values=values,
            line_rows=line_rows,
            flags=_flags_of(record),
            errors=result["errors"],
            warnings=result["warnings"],
            dup_ids=[],
        ), 400

    # Duplicate gate (US-S3-06): saved records with the same vendor + number,
    # or the same file content, require explicit confirmation.
    header = result["data"]["header"]
    conn = get_db()
    try:
        duplicates = find_saved_duplicates(
            conn,
            header.get("vendor") or "",
            header.get("invoice_number") or "",
            exclude_id=invoice_id,
        )
    finally:
        conn.close()
    duplicates = list(duplicates) + _saved_hash_duplicates(record)
    if duplicates and not request.form.get("confirm_duplicate"):
        values, line_rows = form_to_view(request.form)
        dup_ids = sorted({row["id"] for row in duplicates})
        return render_template(
            "review.html",
            invoice=record,
            values=values,
            line_rows=line_rows,
            flags=_flags_of(record),
            errors={},
            warnings=result["warnings"]
            + ["This invoice may be a duplicate — see the warning above."],
            dup_ids=dup_ids,
        ), 409

    conn = get_db()
    try:
        save_invoice(
            conn, invoice_id, header=header, lines=result["data"]["lines"]
        )
    except Exception:  # noqa: BLE001 — rollback already happened
        flash(f"Save failed for record #{invoice_id}; nothing was changed.", "error")
        return redirect(url_for("uploads.index"))

    for warning in result["warnings"]:
        flash(warning, "warning")
    flash(f"Invoice #{invoice_id} saved.", "success")
    return redirect(url_for("uploads.index"))


# ------------------------------------------------------- Sprint 4: history

@bp.get("/invoices")
def history():
    """Saved invoices only, newest first, optional search, minimal paging."""
    q = (request.args.get("q") or "").strip()
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    conn = get_db()
    try:
        rows = list_saved(conn, q=q or None, limit=PAGE_SIZE,
                          offset=(page - 1) * PAGE_SIZE)
        total = count_saved(conn, q=q or None)
    finally:
        conn.close()
    return render_template(
        "history.html",
        rows=rows,
        q=q,
        total=total,
        page=page,
        pages=max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
    )


@bp.get("/invoices/<int:invoice_id>")
def detail(invoice_id: int):
    record = _load(invoice_id)
    if record is None:
        abort(404)
    if record["status"] != "saved":
        flash(
            f"Record #{invoice_id} is {record['status']} — details are "
            "available for saved invoices.",
            "warning",
        )
        return redirect(url_for("uploads.index"))
    conn = get_db()
    try:
        lines = get_lines(conn, invoice_id)
    finally:
        conn.close()
    return render_template("detail.html", invoice=record, lines=lines)


@bp.get("/invoices/<int:invoice_id>/original")
def original(invoice_id: int):
    """Serve the stored source file. The stored name is server-generated and
    send_from_directory refuses paths escaping the uploads directory."""
    record = _load(invoice_id)
    if record is None:
        abort(404)
    return send_from_directory(
        current_app.config["UPLOAD_DIR"],
        record["stored_filename"],
        mimetype="application/pdf",
    )


@bp.post("/invoices/<int:invoice_id>/delete")
def delete(invoice_id: int):
    """POST-only, confirmation-required deletion of saved invoices.
    GET requests never reach this route (405) and never delete."""
    record = _load(invoice_id)
    if record is None:
        abort(404)
    if record["status"] != "saved":
        flash(
            f"Record #{invoice_id} is {record['status']} — only saved "
            "invoices can be deleted.",
            "warning",
        )
        return redirect(url_for("uploads.index"))

    if not request.form.get("confirm_delete"):
        conn = get_db()
        try:
            lines = get_lines(conn, invoice_id)
        finally:
            conn.close()
        return render_template(
            "confirm_delete.html", invoice=record, lines=lines
        )

    ok, message = delete_saved_invoice(invoice_id)
    flash(message, "success" if ok else "error")
    if ok:
        return redirect(url_for("invoices.history"))
    return redirect(url_for("uploads.index"))
