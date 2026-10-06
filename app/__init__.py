"""Invoice Extractor — app factory.

Local-only web application for uploading invoices, extracting their details,
reviewing them, and storing them in a local database. Architecture and sprint
plan: docs/03-plan.md.
"""
from flask import Flask, render_template

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

    # Blueprints are registered as their sprints deliver them (plan §7):
    # Sprint 1 → routes/uploads.py, Sprint 3/4 → routes/invoices.py.

    @app.route("/")
    def index():
        # Sprint 0 placeholder — Sprint 1 replaces this with the upload page
        # served by the uploads blueprint.
        return render_template("index.html")

    return app
