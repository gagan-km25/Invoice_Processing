"""Session role switching — Sprint E4 (ARCHITECTURE §6).

POST-only, allowlist-guarded. Not authentication: this chooses which
workflow role the browser acts as; the header UI shows the current role.
"""
from flask import (
    Blueprint,
    flash,
    redirect,
    request,
    session,
    url_for,
)

from app.services.roles import ALL_ROLES

bp = Blueprint("session", __name__)


@bp.post("/session/role")
def set_role():
    """Switch the session's workflow role (vendor / approver:manager /
    approver:finance). Unknown values are refused — the session keeps its
    previous role."""
    role = (request.form.get("role") or "").strip()
    if role not in ALL_ROLES:
        flash(
            f"Unknown role {role!r} — choose one of: {', '.join(ALL_ROLES)}.",
            "error",
        )
        return redirect(url_for("uploads.index")), 400
    session["role"] = role
    session.modified = True
    flash(f"You are now acting as {role}.", "info")
    return redirect(url_for("uploads.index"))
