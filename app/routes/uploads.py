"""Upload routes (Sprint 1; async since Sprint E1): home page with upload
form + recent uploads, and POST /upload.

Thin HTTP layer — gate logic lives in services/uploading. Since Sprint E1
the upload request does NOT extract: it stores the file + record, audits
`invoice_uploaded`, enqueues a background job (single serial worker), and
returns immediately. The invoice detail page shows live processing status.
"""
from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from app.db import get_db
from app.db.repository import find_by_hash, list_recent
from app.services.pipeline import JOB_NEW_UPLOAD, record_upload_event
from app.services.uploading import UploadRejected, store_upload

bp = Blueprint("uploads", __name__)


@bp.get("/")
def index():
    conn = get_db()
    try:
        recent = list_recent(conn)
    finally:
        conn.close()
    return render_template("index.html", recent=recent)


@bp.post("/upload")
def upload():
    try:
        invoice = store_upload(request.files.get("file"))
    except UploadRejected as exc:
        flash(exc.user_message, "error")
        return redirect(url_for("uploads.index"))

    record_upload_event(invoice["id"])

    duplicates = []
    conn = get_db()
    try:
        duplicates = find_by_hash(conn, invoice["file_hash"], exclude_id=invoice["id"])
    finally:
        conn.close()

    enqueued = current_app.extensions["invoice_worker"].enqueue(
        invoice["id"], JOB_NEW_UPLOAD
    )
    flash(f"Uploaded successfully (record #{invoice['id']}).", "success")
    if duplicates:
        ids = ", ".join(f"#{row['id']}" for row in duplicates)
        flash(
            f"Note: this exact file was uploaded before (record {ids}). "
            "It was stored again anyway.",
            "warning",
        )
    if enqueued:
        flash(
            "Processing continues in the background — this page shows the "
            "current status.",
            "info",
        )
    return redirect(url_for("invoices.detail", invoice_id=invoice["id"]))
