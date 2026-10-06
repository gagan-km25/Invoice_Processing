"""Upload routes (Sprint 1): home page with upload form + recent uploads,
and POST /upload. Thin HTTP layer — gate logic lives in services/uploading.
"""
from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from app.db import get_db
from app.db.repository import find_by_hash, list_recent
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

    conn = get_db()
    try:
        duplicates = find_by_hash(conn, invoice["file_hash"], exclude_id=invoice["id"])
    finally:
        conn.close()

    flash(f"Uploaded successfully (record #{invoice['id']}).", "success")
    if duplicates:
        ids = ", ".join(f"#{row['id']}" for row in duplicates)
        flash(
            f"Note: this exact file was uploaded before (record {ids}). "
            "It was stored again anyway.",
            "warning",
        )
    return redirect(url_for("uploads.index"))
