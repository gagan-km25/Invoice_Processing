"""Session role labels — Sprint E4 (ARCHITECTURE §6, approved correction 4).

A workflow mechanism, NOT authentication: any browser user can switch
roles; guards prevent *wrong-role actions* on this localhost single-user
app, never identity claims. Audit actor values follow audit.py's
convention (`vendor` / `approver:manager` / `approver:finance`), while
`invoices.approver_role` stores the routing value (`manager` / `finance`)
produced by workflow.required_approver — `approver_role_for` bridges the
two.
"""
from flask import session

ROLE_VENDOR = "vendor"
ROLE_MANAGER = "approver:manager"
ROLE_FINANCE = "approver:finance"

ALL_ROLES = (ROLE_VENDOR, ROLE_MANAGER, ROLE_FINANCE)
APPROVER_ROLES = (ROLE_MANAGER, ROLE_FINANCE)
DEFAULT_ROLE = ROLE_VENDOR


def current_role() -> str:
    """The session's role label; the vendor default when unset/unknown."""
    role = session.get("role")
    return role if role in ALL_ROLES else DEFAULT_ROLE


def approver_role_for(role: str | None) -> str | None:
    """`approver:manager` → `manager`, `approver:finance` → `finance`,
    None for the vendor (or any non-approver)."""
    if role == ROLE_MANAGER:
        return "manager"
    if role == ROLE_FINANCE:
        return "finance"
    return None
