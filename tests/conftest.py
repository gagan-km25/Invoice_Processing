"""Shared test fixtures.

Every test runs against a temporary database and temporary directories under
pytest's tmp_path — real data (data/invoices.db, uploads/) is never touched
(NFR-8). Fixtures grow as sprints add functionality.
"""
import io
from types import SimpleNamespace

import pytest
from flask import current_app
from werkzeug.datastructures import FileStorage

from app import create_app
from app.config import Config


def _test_config(tmp_path):
    """Real config with all paths redirected into tmp_path. The worker runs
    in manual mode (no thread): tests drive it deterministically via
    `worker.run_pending()`."""
    base = {name: getattr(Config, name) for name in dir(Config) if name.isupper()}
    base.update(
        TESTING=True,
        DEBUG=False,
        SECRET_KEY="test-secret",
        DATA_DIR=tmp_path / "data",
        UPLOAD_DIR=tmp_path / "uploads",
        SAMPLE_DIR=tmp_path / "samples",
        LOG_DIR=tmp_path / "data" / "logs",
        DATABASE=tmp_path / "data" / "invoices.db",
        WORKER_AUTOSTART=False,
        WORKER_RETRY_BACKOFF_SECONDS=0,
    )
    return SimpleNamespace(**base)


@pytest.fixture()
def app(tmp_path):
    application = create_app(_test_config(tmp_path))
    yield application


@pytest.fixture()
def make_app_config(tmp_path):
    """make_app_config(database=None) -> config for create_app against an
    arbitrary database file (Sprint E0 migration tests point this at a
    copied fixture database; None = the tmp_path default)."""

    def _make(database=None):
        config = _test_config(tmp_path)
        if database is not None:
            config.DATABASE = database
        return config

    return _make


@pytest.fixture()
def client(app):
    return app.test_client()


# --------------------------------------------------------------------------
# PDF test factory — builds structurally valid PDFs from raw syntax (header,
# objects, xref table with computed offsets, trailer). No creation library is
# needed, and the output is a genuine PDF that pdfplumber parses normally.
# Sprint 2 will extend this with text content for extraction fixtures.
# --------------------------------------------------------------------------

def _pdf_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _write_pdf(path, pages: int, text_lines: list[str] | None = None) -> bytes:
    """Build a structurally valid PDF; with `text_lines`, pages carry real
    extractable text (one line per visual row) via simple content streams.

    Object layout: 1 catalog, 2 page-tree, 3 font, then per page a page
    object (even) and a content object (odd).
    """
    kids = " ".join(f"{4 + i * 2} 0 R" for i in range(pages))
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>".encode(),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for i in range(pages):
        page_number, content_number = 4 + i * 2, 5 + i * 2
        if text_lines:
            parts = [b"BT /F1 11 Tf 72 740 Td 16 TL"]
            for line in text_lines:
                parts.append(f"({_pdf_escape(line)}) Tj T*".encode())
            stream = b" ".join(parts) + b" ET"
        else:
            stream = b""
        objects[page_number] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> "
            f"/Contents {content_number} 0 R >>"
        ).encode()
        objects[content_number] = (
            # Exact /Length, no padding newline between data and endstream:
            # pdfium (Sprint E2 rasterization) rejects a Length mismatch that
            # pdfminer tolerates.
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"endstream"
        )

    out = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += f"{number} 0 obj\n".encode() + objects[number] + b"\nendobj\n"

    xref_position = len(out)
    count = max(objects) + 1
    out += f"xref\n0 {count}\n".encode()
    out += b"0000000000 65535 f \n"
    for number in range(1, count):
        out += f"{offsets[number]:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {count} /Root 1 0 R >>\n"
        f"startxref\n{xref_position}\n%%EOF\n"
    ).encode()
    data = bytes(out)
    path.write_bytes(data)
    return data


@pytest.fixture()
def make_pdf(tmp_path):
    """make_pdf(name, pages=1, text_lines=None) -> (Path, bytes) of a valid PDF."""

    def _make(name: str = "sample.pdf", pages: int = 1, text_lines=None):
        path = tmp_path / name
        return path, _write_pdf(path, pages, text_lines)

    return _make


@pytest.fixture()
def pdf_storage(make_pdf):
    """pdf_storage(...) -> FileStorage of a valid PDF, ready for store_upload."""

    def _make(name: str = "sample.pdf", pages: int = 1, data: bytes | None = None):
        _, pdf_bytes = make_pdf(name, pages) if data is None else (None, data)
        return FileStorage(
            stream=io.BytesIO(pdf_bytes), filename=name, content_type="application/pdf"
        )

    return _make


@pytest.fixture()
def app_context(app):
    """Push an app context so services using current_app work in unit tests."""
    with app.app_context():
        yield app


@pytest.fixture()
def worker(app):
    """The app's invoice worker in manual mode (WORKER_AUTOSTART=False):
    tests call `worker.run_pending()` to drain the queue deterministically,
    or `worker.process_job(id, kind)` for claim-ladder cases."""
    return app.extensions["invoice_worker"]


@pytest.fixture()
def db_rows(app):
    """Direct query helper: all rows of the invoices table, oldest first."""
    import sqlite3

    def _rows():
        conn = sqlite3.connect(app.config["DATABASE"])
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute("SELECT * FROM invoices ORDER BY id").fetchall()
        finally:
            conn.close()

    return _rows
