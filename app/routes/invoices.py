"""Invoice review, save, history, detail, and lifecycle routes (Sprint 3;
async lifecycle since Sprint E1). Thin HTTP layer: validation/merge lives
in services/review.py, the transaction in the repository, transitions in
services/workflow.py via the pipeline.

Guards: 404 for unknown ids; review/save accept `extracted` (legacy rows)
or `completed` (pipeline output); only `saved` records can be deleted;
duplicates require explicit confirmation (US-S3-06); reprocess is offered
for `failed` records (and `validation_failed` once Sprint E3 adds it).
"""
import json

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)

from app.db import get_db
from app.db.repository import (
    count_invoices,
    find_by_hash,
    find_duplicate_records,
    get_audit,
    get_invoice,
    get_lines,
    list_invoices,
    save_invoice,
)
from app.services import approvals
from app.services.invoices import delete_invoice_record
from app.services.pipeline import JOB_REPROCESS
from app.services.review import (
    form_to_view,
    prefill_from_draft,
    validate_and_merge,
    with_blank_rows,
)
from app.services.roles import ROLE_VENDOR, current_role

REVIEWABLE = ("extracted", "completed")

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


def _hash_duplicates(record) -> list:
    """Other records with the same file content, in any status, excluding
    this record (Sprint E5 rewire — duplicate detection is status-blind)."""
    conn = get_db()
    try:
        return list(
            find_by_hash(conn, record["file_hash"], exclude_id=record["id"])
        )
    finally:
        conn.close()


@bp.get("/invoices/<int:invoice_id>/status")
def status(invoice_id: int):
    """JSON processing status (Sprint E1) — used by the detail page poll."""
    record = _load(invoice_id)
    if record is None:
        abort(404)
    return jsonify(
        {
            "id": record["id"],
            "status": record["status"],
            "updated_at": record["updated_at"],
        }
    )


@bp.post("/invoices/<int:invoice_id>/reprocess")
def reprocess(invoice_id: int):
    """Re-run the pipeline for a failed (or, from Sprint E3,
    validation-failed) invoice. The route only guards + enqueues; the
    worker's claim ladder performs T5/T5b and audits `reprocess_requested`
    in the same transaction as the status change."""
    if current_role() != ROLE_VENDOR:
        abort(403)  # route map: reprocess is a vendor action (ARCHITECTURE §6)
    record = _load(invoice_id)
    if record is None:
        abort(404)
    if record["status"] not in ("failed", "validation_failed"):
        flash(
            f"Record #{invoice_id} is {record['status']} — only failed "
            "invoices can be reprocessed.",
            "warning",
        )
        return redirect(url_for("invoices.detail", invoice_id=invoice_id))
    current_app.extensions["invoice_worker"].enqueue(invoice_id, JOB_REPROCESS)
    flash(f"Reprocessing record #{invoice_id}.", "info")
    return redirect(url_for("invoices.detail", invoice_id=invoice_id))


@bp.post("/invoices/<int:invoice_id>/submit")
def submit(invoice_id: int):
    """Submit a completed (or validation-failed) invoice for approval
    (Sprint E4, assignment §10): route by amount and persist
    `approver_role` + audits in one transaction. Vendor-only per the
    route map; NULL totals are refused (routing needs the amount —
    approved decision 1, never default to Finance)."""
    if current_role() != ROLE_VENDOR:
        abort(403)  # route map: submission is a vendor action
    record = _load(invoice_id)
    if record is None:
        abort(404)
    threshold = current_app.config["APPROVAL_THRESHOLD"]
    conn = get_db()
    try:
        result = approvals.submit(conn, invoice_id, threshold=threshold)
    finally:
        conn.close()
    if result["ok"]:
        flash(
            f"Record #{invoice_id} submitted — routed to the "
            f"{result['approver_role']} approver.",
            "success",
        )
    else:
        flash(result["error"], "warning")
    return redirect(url_for("invoices.detail", invoice_id=invoice_id))


@bp.get("/invoices/<int:invoice_id>/review")
def review(invoice_id: int):
    if current_role() != ROLE_VENDOR:
        abort(403)  # route map: review is a vendor action (ARCHITECTURE §6)
    record = _load(invoice_id)
    if record is None:
        abort(404)
    if record["status"] not in REVIEWABLE:
        flash(
            f"Record #{invoice_id} is {record['status']} — only extracted "
            "or completed invoices can be reviewed.",
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
    if current_role() != ROLE_VENDOR:
        abort(403)  # route map: save is a vendor action (ARCHITECTURE §6)
    record = _load(invoice_id)
    if record is None:
        abort(404)
    if record["status"] not in REVIEWABLE:
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

    # Duplicate gate (US-S3-06, rewired Sprint E5): other records with the
    # same vendor + number, or the same file content, in any status,
    # require explicit confirmation.
    header = result["data"]["header"]
    conn = get_db()
    try:
        duplicates = find_duplicate_records(
            conn,
            header.get("vendor") or "",
            header.get("invoice_number") or "",
            exclude_id=invoice_id,
        )
    finally:
        conn.close()
    duplicates = list(duplicates) + _hash_duplicates(record)
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
    """All invoices (Sprint E5, assignment §14), optional exact-status
    filter and search, newest invoice date first, minimal paging."""
    q = (request.args.get("q") or "").strip()
    status = request.args.get("status") or None
    if status not in current_app.config["INVOICE_STATUSES"]:
        status = None  # unknown filter values are ignored, not errors
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    conn = get_db()
    try:
        rows = list_invoices(conn, status=status, q=q or None,
                             limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE)
        total = count_invoices(conn, status=status, q=q or None)
    finally:
        conn.close()
    return render_template(
        "history.html",
        rows=rows,
        q=q,
        status=status,
        statuses=current_app.config["INVOICE_STATUSES"],
        total=total,
        page=page,
        pages=max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
    )


@bp.get("/invoices/<int:invoice_id>")
def detail(invoice_id: int):
    """Invoice detail — available for every status since Sprint E1 (the
    upload redirect lands here so processing progress is visible).
    Sprint E3: business-validation verdict/findings and duplicate
    classification. Sprint E5: audit timeline and the retained raw
    provider response (collapsed + escaped, never while processing)."""
    record = _load(invoice_id)
    if record is None:
        abort(404)
    conn = get_db()
    try:
        lines = get_lines(conn, invoice_id)
        audit_entries = get_audit(conn, invoice_id)
    finally:
        conn.close()

    def _json_column(raw):
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except ValueError:
            return []
        return parsed if isinstance(parsed, list) else []

    validation_findings = _json_column(record["validation_json"])
    dup_matches = _json_column(record["dup_matches"])
    raw_response = (
        record["raw_response"]
        if record["status"] not in ("uploaded", "processing")
        else None
    )
    return render_template(
        "detail.html",
        invoice=record,
        lines=lines,
        validation_findings=validation_findings,
        dup_matches=dup_matches,
        audit_entries=audit_entries,
        raw_response=raw_response,
    )


@bp.get("/invoices/<int:invoice_id>/original")
def original(invoice_id: int):
    """Serve the stored source file. The stored name is server-generated and
    send_from_directory refuses paths escaping the uploads directory. The
    MIME type follows the stored `file_type` (Sprint E2: images)."""
    record = _load(invoice_id)
    if record is None:
        abort(404)
    extension = (record["stored_filename"] or "").rsplit(".", 1)[-1].lower()
    if record["file_type"] == "image" and extension in ("jpg", "jpeg"):
        mimetype = "image/jpeg"
    elif record["file_type"] == "image":
        mimetype = "image/png"
    else:
        mimetype = "application/pdf"
    return send_from_directory(
        current_app.config["UPLOAD_DIR"],
        record["stored_filename"],
        mimetype=mimetype,
    )


@bp.post("/invoices/<int:invoice_id>/delete")
def delete(invoice_id: int):
    """POST-only, confirmation-required deletion (Sprint E5 policy:
    blocked while `uploaded`/`processing`, allowed otherwise).
    GET requests never reach this route (405) and never delete."""
    if current_role() != ROLE_VENDOR:
        abort(403)  # route map: delete is a vendor action (ARCHITECTURE §6)
    record = _load(invoice_id)
    if record is None:
        abort(404)
    if record["status"] in ("uploaded", "processing"):
        flash(
            f"Record #{invoice_id} is {record['status']} — it cannot be "
            "deleted while queued or processing.",
            "warning",
        )
        return redirect(url_for("invoices.detail", invoice_id=invoice_id))

    if not request.form.get("confirm_delete"):
        conn = get_db()
        try:
            lines = get_lines(conn, invoice_id)
        finally:
            conn.close()
        return render_template(
            "confirm_delete.html", invoice=record, lines=lines
        )

    ok, message = delete_invoice_record(invoice_id)
    flash(message, "success" if ok else "error")
    if ok:
        return redirect(url_for("invoices.history"))
    return redirect(url_for("invoices.detail", invoice_id=invoice_id))
