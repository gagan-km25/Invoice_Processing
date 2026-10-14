"""Structured application logging (approved plan §8; Sprint E1).

Exactly two application loggers:
- `app.events` — lifecycle events via `log_event()`, whose keyword fields
  are validated against an allowlist. It cannot receive free-form payloads
  (a non-allowlisted field raises), and it never receives `exc_info`, so
  exception text cannot reach it.
- `app.errors` — the ONLY logger permitted to record tracebacks. Callers
  must pass either a plain template message (no interpolated data) or a
  boundary-sanitised exception (e.g. pipeline.PipelineError, whose message
  is a fixed template and whose cause is suppressed). Raw third-party
  exceptions must never be passed here.

Both loggers write to rotating files under LOG_DIR (git-ignored) and the
console. `configure_logging` re-points the handlers on every app creation
so concurrent test apps never write into each other's temporary
directories.
"""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

EVENTS_LOGGER = "app.events"
ERRORS_LOGGER = "app.errors"

# The complete set of fields any log_event call may carry. Values are
# identifiers, status names, counts, or HTTP-style codes — never message
# text, exception strings, invoice content, or provider bodies.
ALLOWED_EVENT_FIELDS = frozenset({
    "invoice_id",
    "job_kind",
    "event_type",
    "from_status",
    "to_status",
    "status",
    "verdict",
    "classification",
    "reason",
    "attempts",
    "error_class",
    "error_status",
    "count",
    "actor",
})

_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def _files(app) -> dict[str, Path]:
    log_dir = Path(app.config["LOG_DIR"])
    return {
        EVENTS_LOGGER: log_dir / "events.log",
        ERRORS_LOGGER: log_dir / "errors.log",
    }


def configure_logging(app) -> None:
    """(Re)point the two application loggers at this app's LOG_DIR."""
    app.config["LOG_DIR"].mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(_FORMAT)
    for name, path in _files(app).items():
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger.handlers.clear()  # one active app at a time (tests re-create)
        handler = RotatingFileHandler(
            path, maxBytes=512 * 1024, backupCount=2, encoding="utf-8"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        logger.addHandler(console)


def log_event(event: str, **fields) -> None:
    """Record one structured lifecycle event. Any field outside the
    allowlist raises — logging cannot silently become a leakage channel."""
    unknown = set(fields) - ALLOWED_EVENT_FIELDS
    if unknown:
        raise ValueError(f"non-allowlisted log field(s): {sorted(unknown)}")
    parts = [f"event={event}"]
    for key in sorted(fields):
        parts.append(f"{key}={fields[key]}")
    logging.getLogger(EVENTS_LOGGER).info(" ".join(parts))


def log_error(message: str, *, exc_info=False) -> None:
    """Record an error. `message` must be a fixed template (ids/counts only);
    `exc_info=True` only for sanitised domain exceptions captured in an
    except block (traceback text then contains template messages only)."""
    logging.getLogger(ERRORS_LOGGER).error(str(message), exc_info=exc_info)


def events_log_path(app) -> Path:
    return _files(app)[EVENTS_LOGGER]


def errors_log_path(app) -> Path:
    return _files(app)[ERRORS_LOGGER]
