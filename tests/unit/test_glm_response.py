"""Sprint E2 unit tests — GLM response → parser-shaped draft conversion
(`extraction.ai_json_to_draft`).

TC-RESP cases: valid schema, code fences, non-JSON, array-not-object,
empty object, wrong field types, bad dates, non-numeric amounts, invalid
line items skipped, unknown fields tolerated.
"""
import json
from decimal import Decimal

import pytest

from app.services.extraction import ai_json_to_draft

VALID = {
    "invoice_number": "INV-G-1",
    "invoice_date": "2026-01-15",
    "due_date": "2026-02-15",
    "vendor": "Acme Corporation",
    "vendor_tax_id": "29AABCT1234F1Z5",
    "bill_to": "Buyer",
    "currency": "usd",
    "subtotal": "1000.00",
    "discount": None,
    "tax": 80,
    "tax_rate": 8,
    "total": 1080,
    "line_items": [
        {"description": "Widget", "quantity": 2, "unit_price": "40.00", "amount": "80.00"},
        {"description": "Gadget", "quantity": 1, "unit_price": 20, "amount": 20},
    ],
    "unknown_field": "must be tolerated",
}


def test_valid_response_builds_parser_shaped_draft():
    draft = ai_json_to_draft(json.dumps(VALID), "glm-test", 2)
    fields = draft["fields"]
    assert fields["invoice_number"] == {"status": "found", "value": "INV-G-1"}
    assert fields["currency"] == {"status": "found", "value": "USD"}
    assert fields["subtotal"]["value"] == Decimal("1000.00")
    assert fields["tax"]["value"] == Decimal("80.00")
    assert fields["tax_rate"]["value"] == Decimal("8.00")
    assert fields["discount"]["status"] == "missing"  # null → missing
    assert fields["due_date"]["value"] == "2026-02-15"
    assert draft["meta"]["source"] == "glm"
    assert draft["meta"]["model"] == "glm-test"
    assert draft["meta"]["page_count"] == 2
    assert draft["checks"] == []
    assert [line["line_number"] for line in draft["lines"]] == [1, 2]
    assert draft["lines"][0]["amount"] == Decimal("80.00")


def test_code_fenced_json_is_accepted():
    draft = ai_json_to_draft("```json\n" + json.dumps(VALID) + "\n```", "glm-test", 1)
    assert draft["fields"]["vendor"]["value"] == "Acme Corporation"


def test_not_json_raises_value_error():
    with pytest.raises(ValueError, match="not valid JSON"):
        ai_json_to_draft("this is not json", "glm-test", 1)


def test_truncated_json_raises_value_error():
    with pytest.raises(ValueError):
        ai_json_to_draft(json.dumps(VALID)[:-5], "glm-test", 1)


def test_array_not_object_raises_value_error():
    with pytest.raises(ValueError, match="not a JSON object"):
        ai_json_to_draft("[]", "glm-test", 1)


def test_line_items_not_array_raises_value_error():
    with pytest.raises(ValueError, match="line_items"):
        ai_json_to_draft(json.dumps({"line_items": "oops"}), "glm-test", 1)


def test_empty_object_is_valid_all_fields_missing():
    draft = ai_json_to_draft("{}", "glm-test", 1)
    for name, field in draft["fields"].items():
        assert field["status"] == "missing", name
    assert draft["lines"] == []


def test_wrong_type_field_degrades_to_missing_with_note():
    draft = ai_json_to_draft(
        json.dumps({"invoice_number": 12345, "vendor": ["a"]}), "glm-test", 1
    )
    assert draft["fields"]["invoice_number"]["status"] == "missing"
    assert draft["fields"]["vendor"]["status"] == "missing"


def test_bad_date_and_non_numeric_degrade_to_missing():
    draft = ai_json_to_draft(
        json.dumps(
            {
                "invoice_date": "15/01/2026",
                "subtotal": "abc",
                "total": None,
            }
        ),
        "glm-test",
        1,
    )
    assert draft["fields"]["invoice_date"]["status"] == "missing"
    assert draft["fields"]["subtotal"]["status"] == "missing"
    assert draft["fields"]["total"]["status"] == "missing"


def test_non_3_letter_currency_degrades_to_missing():
    draft = ai_json_to_draft(json.dumps({"currency": "dollars"}), "glm-test", 1)
    assert draft["fields"]["currency"]["status"] == "missing"


def test_invalid_line_items_are_skipped_and_numbering_continues():
    payload = {
        "line_items": [
            {"description": "Good", "quantity": 1, "unit_price": 10, "amount": 10},
            "not a dict",
            {"description": "Missing price", "quantity": 1},
            {"description": "Also good", "quantity": 2, "unit_price": 5, "amount": 10},
        ]
    }
    draft = ai_json_to_draft(json.dumps(payload), "glm-test", 1)
    assert [line["description"] for line in draft["lines"]] == ["Good", "Also good"]
    assert [line["line_number"] for line in draft["lines"]] == [1, 2]
