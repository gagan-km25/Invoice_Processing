"""Application configuration.

Values locked by approved decisions (docs/02-exploration §20, docs/03-plan §8):
localhost-only binding, DEBUG with reloader off (Windows), 10 MB upload cap,
50-page extraction cap.
"""
import os
from decimal import Decimal
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
    # Env-overridable so a real deployment never needs a committed key.
    SECRET_KEY = os.environ.get("SECRET_KEY", "local-dev-only")

    # Upload/extraction limits (T-H).
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB
    PAGE_LIMIT = 50

    # AI extraction (Z.ai GLM) — Sprint E0 configuration plumbing only; the
    # client itself arrives in Sprint E2. The API key is read from the
    # environment exclusively: never hard-coded, never committed, never
    # logged. See .env.example for the supported variables.
    ZAI_API_KEY = os.environ.get("ZAI_API_KEY", "")
    ZAI_BASE_URL = os.environ.get("ZAI_BASE_URL", "https://api.z.ai/api/paas/v4/")
    ZAI_TEXT_MODEL = os.environ.get("ZAI_TEXT_MODEL", "glm-4.6")
    ZAI_VISION_MODEL = os.environ.get("ZAI_VISION_MODEL", "glm-4.5v")
    ZAI_TIMEOUT_SECONDS = int(os.environ.get("ZAI_TIMEOUT_SECONDS", "60"))

    # Business rules (enhancement assignment §10/§8.2; approved plan §C).
    # Approval routing: total < threshold → manager, else finance. The
    # threshold is a Decimal so comparisons stay exact at the boundary.
    APPROVAL_THRESHOLD = Decimal("100000.00")
    # Rounding tolerance for amount-consistency validation (assignment §8.2).
    VALIDATION_TOLERANCE = Decimal("0.01")

    # Invoice lifecycle (enhancement assignment §5/§12). The single source of
    # truth for valid statuses; transitions are controlled by
    # app/services/workflow.py. `extracted`/`saved` are NOT valid states —
    # they appear only in the schema's transitional CHECK (see schema.sql).
    INVOICE_STATUSES = (
        "uploaded",
        "processing",
        "completed",
        "validation_failed",
        "pending_approval",
        "approved",
        "rejected",
        "failed",
    )

    # Paths (data dirs are git-ignored; created on boot).
    DATA_DIR = BASE_DIR / "data"
    UPLOAD_DIR = BASE_DIR / "uploads"
    SAMPLE_DIR = BASE_DIR / "sample_invoices"
    DATABASE = DATA_DIR / "invoices.db"
    SCHEMA = BASE_DIR / "app" / "db" / "schema.sql"
