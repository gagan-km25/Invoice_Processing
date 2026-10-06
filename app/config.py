"""Application configuration.

Values locked by approved decisions (docs/02-exploration §20, docs/03-plan §8):
localhost-only binding, DEBUG with reloader off (Windows), 10 MB upload cap,
50-page extraction cap.
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    # Network — never bind to 0.0.0.0 (NFR-1). DEBUG tooling is acceptable
    # only because of this binding; change them together (exploration §12).
    HOST = "127.0.0.1"
    PORT = 5000
    DEBUG = True
    USE_RELOADER = False  # reloader spawns child processes; problematic on Windows

    # Flash-message signing only — no sensitive session data in this app.
    SECRET_KEY = "local-dev-only"

    # Upload/extraction limits (T-H).
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB
    PAGE_LIMIT = 50

    # Paths (data dirs are git-ignored; created on boot).
    DATA_DIR = BASE_DIR / "data"
    UPLOAD_DIR = BASE_DIR / "uploads"
    SAMPLE_DIR = BASE_DIR / "sample_invoices"
    DATABASE = DATA_DIR / "invoices.db"
    SCHEMA = BASE_DIR / "app" / "db" / "schema.sql"
