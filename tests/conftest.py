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
    """Real config with all paths redirected into tmp_path."""
    base = {name: getattr(Config, name) for name in dir(Config) if name.isupper()}
    base.update(
        TESTING=True,
        DEBUG=False,
        SECRET_KEY="test-secret",
        DATA_DIR=tmp_path / "data",
        UPLOAD_DIR=tmp_path / "uploads",
        SAMPLE_DIR=tmp_path / "samples",
        DATABASE=tmp_path / "data" / "invoices.db",
    )
    return SimpleNamespace(**base)


@pytest.fixture()
def app(tmp_path):
    application = create_app(_test_config(tmp_path))
    yield application


@pytest.fixture()
def client(app):
    return app.test_client()


# --------------------------------------------------------------------------
# PDF test factory — builds structurally valid PDFs from raw syntax (header,
# objects, xref table with computed offsets, trailer). No creation library is
# needed, and the output is a genuine PDF that pdfplumber parses normally.
# Sprint 2 will extend this with text content for extraction fixtures.
# --------------------------------------------------------------------------

def _write_pdf(path, pages: int) -> bytes:
    kids = " ".join(f"{number} 0 R" for number in range(3, 3 + pages))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>".encode(),
    ]
    objects += [
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>"
        for _ in range(pages)
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_position = len(out)
    count = len(objects) + 1
    out += f"xref\n0 {count}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {count} /Root 1 0 R >>\n"
        f"startxref\n{xref_position}\n%%EOF\n"
    ).encode()
    data = bytes(out)
    path.write_bytes(data)
    return data


@pytest.fixture()
def make_pdf(tmp_path):
    """make_pdf(name="sample.pdf", pages=1) -> Path of a valid PDF in tmp_path."""

    def _make(name: str = "sample.pdf", pages: int = 1):
        return tmp_path / name, _write_pdf(tmp_path / name, pages)

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
