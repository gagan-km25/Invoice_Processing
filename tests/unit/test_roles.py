"""Sprint E4 unit tests — session role labels and the approver mapping
(`app/services/roles.py`; ARCHITECTURE §6, approved correction 4)."""
import pytest
from flask import session

from app.services.roles import (
    ALL_ROLES,
    DEFAULT_ROLE,
    ROLE_FINANCE,
    ROLE_MANAGER,
    ROLE_VENDOR,
    approver_role_for,
    current_role,
)


def test_all_roles_catalogued():
    """Exactly the three documented labels exist; vendor is the default."""
    assert ALL_ROLES == (ROLE_VENDOR, ROLE_MANAGER, ROLE_FINANCE)
    assert DEFAULT_ROLE == ROLE_VENDOR


def test_current_role_defaults_to_vendor_when_unset(app):
    with app.test_request_context():
        assert "role" not in session
        assert current_role() == ROLE_VENDOR


def test_current_role_ignores_unknown_values(app):
    """Anything not on the allowlist falls back to the vendor default —
    a poisoned session can never produce an unknown role."""
    with app.test_request_context():
        session["role"] = "intruder"
        assert current_role() == ROLE_VENDOR


@pytest.mark.parametrize("role,expected", [
    (ROLE_VENDOR, ROLE_VENDOR),
    (ROLE_MANAGER, ROLE_MANAGER),
    (ROLE_FINANCE, ROLE_FINANCE),
])
def test_current_role_reads_session(app, role, expected):
    with app.test_request_context():
        session["role"] = role
        assert current_role() == expected


def test_approver_role_mapping():
    """approver:manager → manager, approver:finance → finance; the vendor
    (or anything unknown) maps to None — a vendor can never act as an
    approver, and `invoices.approver_role` stores the routing value."""
    assert approver_role_for(ROLE_MANAGER) == "manager"
    assert approver_role_for(ROLE_FINANCE) == "finance"
    assert approver_role_for(ROLE_VENDOR) is None
    assert approver_role_for("intruder") is None
    assert approver_role_for(None) is None
