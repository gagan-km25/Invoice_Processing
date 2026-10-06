"""Sprint 0 smoke tests (plan S0-T6): the app boots, serves the home page,
and the database schema exists."""
import sqlite3


def test_app_boots(app):
    assert app is not None
    assert app.config["TESTING"] is True
    assert app.config["DATABASE"].exists()


def test_home_page_returns_200(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Invoice Extractor" in response.data


def test_schema_tables_exist(app):
    with app.app_context():
        conn = sqlite3.connect(app.config["DATABASE"])
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        finally:
            conn.close()
    table_names = {row[0] for row in rows}
    assert {"invoices", "invoice_lines"} <= table_names
