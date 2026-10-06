"""Shared test fixtures.

Every test runs against a temporary database and temporary directories under
pytest's tmp_path — real data (data/invoices.db, uploads/) is never touched
(NFR-8). Fixtures grow as sprints add functionality.
"""
from types import SimpleNamespace

import pytest

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
