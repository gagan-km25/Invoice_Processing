"""Invoice Extractor — app factory.

Local-only web application for uploading invoices, extracting their details,
reviewing them, and storing them in a local database. Architecture and sprint
plan: docs/03-plan.md.
"""
from urllib.parse import urlsplit

from flask import Flask, flash, redirect, request, url_for
from werkzeug.exceptions import RequestEntityTooLarge

from app.config import Config
from app.db import init_db


def create_app(config_object=Config) -> Flask:
    """Create and configure the app; boot-time setup is zero-manual-step."""
    app = Flask(__name__)
    app.config.from_object(config_object)

    # Local dirs (created idempotently; git-ignored — see .gitignore).
    app.config["DATA_DIR"].mkdir(parents=True, exist_ok=True)
    app.config["UPLOAD_DIR"].mkdir(parents=True, exist_ok=True)
    app.config["SAMPLE_DIR"].mkdir(parents=True, exist_ok=True)

    # SQLite schema (idempotent — safe on every boot).
    init_db(app)

    from app.routes import invoices, uploads

    app.register_blueprint(uploads.bp)
    app.register_blueprint(invoices.bp)

    @app.before_request
    def reject_cross_site_posts():
        """T-G: a malicious webpage in the same browser can post forms at
        127.0.0.1 — reject any POST whose Origin host is not this host.
        Loopback spellings (localhost / 127.0.0.1 / ::1) are equivalent here.
        Non-browser clients (curl) omit Origin and are allowed; the app is
        localhost-only regardless (NFR-1)."""
        if request.method != "POST":
            return None
        origin = request.headers.get("Origin")
        if not origin:
            return None
        origin_host = (urlsplit(origin).hostname or "").lower()
        local_host = (urlsplit(f"//{request.host}").hostname or "").lower()
        loopback = {"localhost", "127.0.0.1", "::1"}
        if origin_host == local_host or (origin_host in loopback and local_host in loopback):
            return None
        return "Cross-origin POST rejected", 403

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_error):
        # Flask rejects bodies over MAX_CONTENT_LENGTH before our route runs;
        # translate the raw 413 into the same friendly flash as other gates.
        limit_mb = app.config["MAX_CONTENT_LENGTH"] / (1024 * 1024)
        flash(f"File is too large. The limit is {limit_mb:.0f} MB.", "error")
        return redirect(url_for("uploads.index"))

    return app
