"""Duplicate classification — assignment §9 (Sprint E3).

Classifies an invoice against other stored invoices:
- Exact duplicate:    case-insensitive supplier name + invoice number.
- Possible duplicate: case-insensitive supplier name + exact total amount
                      + exact invoice date.
- Otherwise:          no duplicate.

The invoice being classified is always excluded from its own candidates.
Classification is informational — duplicates never block processing; the
stored explanation names each matched record so the user can decide.

Candidate set (approved decision C): invoices in `completed`,
`validation_failed`, `pending_approval`, `saved`, `approved`, or
`rejected` — i.e. every state with structured field values except the
invoice itself. `uploaded`/`processing` rows carry no comparable fields.
Candidates are fetched via repository.find_duplicate_candidates (all SQL
lives in the repository — architecture rule).
"""
from decimal import Decimal

from app.db.repository import find_duplicate_candidates, get_invoice

CLASSIFICATION_NONE = "none"
CLASSIFICATION_POSSIBLE = "possible"
CLASSIFICATION_EXACT = "exact"


def _q2(value):
    """2dp Decimal for exact-total comparison, or None."""
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except Exception:
        return None


def _norm(value):
    return (value or "").strip().casefold()


def classify(conn, invoice_id) -> dict:
    """Classify invoice `invoice_id` against other stored invoices.

    Returns {"classification": ..., "matches": [...]} where each match
    carries {"id", "vendor", "invoice_number", "invoice_date", "total",
    "kind", "reason"} and kind is "exact" or "possible".
    """
    record = get_invoice(conn, invoice_id)
    if record is None:
        return {"classification": "none", "matches": []}

    vendor = _norm(record["vendor"])
    number = _norm(record["invoice_number"])
    if not vendor or not number:
        return {"classification": "none", "matches": []}

    rows = find_duplicate_candidates(conn, invoice_id)

    matches = []
    for row in rows:
        cand_vendor = _norm(row["vendor"])
        cand_number = _norm(row["invoice_number"])
        if vendor == cand_vendor and number == cand_number:
            matches.append({
                "id": row["id"],
                "vendor": row["vendor"],
                "invoice_number": row["invoice_number"],
                "invoice_date": row["invoice_date"],
                "total": row["total"],
                "kind": "exact",
            })
        elif (
            vendor == cand_vendor
            and _q2(record["total"]) is not None
            and _q2(record["total"]) == _q2(row["total"])
            and record["invoice_date"] is not None
            and record["invoice_date"] == row["invoice_date"]
        ):
            matches.append({
                "id": row["id"],
                "vendor": row["vendor"],
                "invoice_number": row["invoice_number"],
                "invoice_date": row["invoice_date"],
                "total": row["total"],
                "kind": "possible",
            })

    if any(m["kind"] == "exact" for m in matches):
        classification = CLASSIFICATION_EXACT
    elif matches:
        classification = CLASSIFICATION_POSSIBLE
    else:
        classification = CLASSIFICATION_NONE
    return {"classification": classification, "matches": matches}
