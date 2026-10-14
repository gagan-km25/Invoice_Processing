"""Field-level extraction strategies.

Every strategy returns a Field dict: {status: found|ambiguous|missing,
value, raw?, evidence?, note?}. Strategies never raise for "not found" —
missing is a normal outcome (FR-6: prefer missing over a guessed found).

Label matching is *contains*-based (exploration: 'Invoice No:' sits mid-line
after the vendor name) with longest-label-first ordering, and requires a
non-alphanumeric boundary after the label so 'GST…' never matches 'GSTIN'
(verified failure mode during Sprint 2 bring-up).
"""
import re

from . import labels
from .normalize import (
    clean,
    detect_currency_symbol,
    parse_amount,
    parse_date,
    parse_invoice_number,
    resolve_currency,
    text_lines,
)


def found(value, **extra):
    return {"status": "found", "value": value, **extra}


def ambiguous(value, **extra):
    return {"status": "ambiguous", "value": value, **extra}


def missing(**extra):
    return {"status": "missing", "value": None, **extra}


def _match_label(line_low: str, label_list: list[str]) -> str | None:
    """Longest label contained in the line with word boundaries on both sides.

    Suffix boundary: 'gst' must not match inside 'gstin'. Prefix boundary:
    'total' must not match inside 'Subtotal' (verified failure mode).
    """
    for label in sorted(label_list, key=len, reverse=True):
        position = line_low.find(label)
        if position == -1:
            continue
        if position > 0 and line_low[position - 1].isalnum():
            continue
        end = position + len(label)
        if end < len(line_low) and line_low[end].isalnum():
            continue
        return label
    return None


def find_labeled_value(lines: list[str], label_list: list[str]) -> str | None:
    """Value following a contained label: '… Invoice No: X' → 'X'."""
    for line in lines:
        low = line.lower()
        label = _match_label(low, label_list)
        if label is None:
            continue
        rest = line[low.find(label) + len(label):].strip(" :#")
        if rest:
            return rest
    return None


def find_summary_amount(lines: list[str], label_list):
    """(context_line, value_part, Decimal|None) for the first label match.

    The value part has any '(18%)'-style rate segment removed so the rate never
    merges into the amount (verified failure mode: '(18%) n1,179.00').
    """
    for line in lines:
        low = line.lower()
        label = _match_label(low, label_list)
        if label is None:
            continue
        rest = line[low.find(label) + len(label):].strip(" :")
        value_part = re.sub(r"\([^)]*%\)", " ", rest)
        amount = parse_amount(value_part)
        if amount is not None:
            return line, value_part, amount
    return None, None, None


def _looks_like_non_vendor(first_line_low: str) -> bool:
    """Header/label cells are not vendor blocks (guards against layouts where
    pdfplumber builds tables from title, labels, or bill-to rows)."""
    if len(first_line_low) < 3 or first_line_low[0].isdigit():
        return True
    if first_line_low in labels.DOC_TITLE_KEYWORDS:
        return True
    for label_list in (
        labels.INVOICE_NO_LABELS,
        labels.INVOICE_DATE_LABELS,
        labels.BILL_TO_LABELS,
        labels.VENDOR_TAX_ID_LABELS,
    ):
        if _match_label(first_line_low, label_list):
            return True
    if any(first_line_low.startswith(k) for k in labels.ITEM_HEADER_KEYWORDS):
        return True  # item-table header cell (verified: 'Description' became
        # the vendor on a real layout whose first table was the items table)
    return False


def extract_vendor_block(tables):
    """(vendor, address, tax_id_line) from the first table's leading cell.

    Reliable source on this layout family: cell = 'vendor\\naddress\\nGSTIN: …'.
    `tables` must be a list of tables (pdfplumber's shape). Returns
    (None, None, None) when no vendor-like cell exists.
    """
    for table in tables or []:
        if not table or not table[0] or not table[0][0]:
            continue
        cell_lines = text_lines(str(table[0][0]))
        if not cell_lines:
            continue
        first = cell_lines[0].lower()
        if _looks_like_non_vendor(first):
            continue  # title/labels/bill-to cell — not a vendor block
        address = cell_lines[1] if len(cell_lines) > 1 else None
        tax_line = next((l for l in cell_lines if "gstin" in l.lower()), None)
        return cell_lines[0], address, tax_line
    return None, None, None


def extract_tax_id(tax_line: str | None, lines: list[str]) -> str | None:
    """GSTIN/VAT/tax-id from a labeled line, searched anywhere as fallback."""
    candidates = [tax_line] if tax_line else []
    candidates.extend(lines)
    for line in candidates:
        match = re.search(
            r"(?i)\b(gstin|gst no|vat no|tax id|abn)\b[:\s#]*([A-Z0-9]{5,20})", line
        )
        if match:
            return match.group(2).upper()
    return None


def extract_bill_to(lines: list[str]) -> str | None:
    """Lines after a bill-to label, stopping at the item-table header."""
    for index, line in enumerate(lines):
        low = line.lower()
        if any(low.startswith(label) for label in labels.BILL_TO_LABELS):
            collected: list[str] = []
            for follow in lines[index + 1:]:
                follow_low = follow.lower()
                stopped = follow_low.startswith(labels.ITEM_HEADER_PREFIXES) or (
                    all(k in follow_low for k in ("description", "qty"))
                )
                if stopped or len(collected) >= 3:
                    break
                collected.append(follow)
            if collected:
                return ", ".join(collected)
    return None


def extract_tax_rate(tax_context: str | None) -> float | None:
    """Rate from a tax label like 'GST (18%)' → 18.0."""
    if not tax_context:
        return None
    match = re.search(r"\((\d+(?:\.\d+)?)\s*%\)", tax_context)
    return float(match.group(1)) if match else None


def _attempt(strategy, *args, default=None):
    """Per-strategy containment: a crash marks that piece missing with a note
    instead of blanking the whole parse (NFR-4)."""
    try:
        return strategy(*args)
    except Exception as exc:  # noqa: BLE001 — deliberate containment
        if default is None:
            return missing(note=f"strategy error: {exc}")
        return default


def _as_field(result):
    """Coerce a strategy result into a Field — _attempt may already have
    returned a missing-with-note Field on containment."""
    if isinstance(result, dict):
        return result
    if result is None:
        return missing()
    return found(result)


def build_fields(text: str, tables) -> dict:
    """All header fields for the draft. Read docs/07 §Phase B for strategy."""
    lines = text_lines(text)

    fields: dict[str, dict] = {}

    # --- vendor / address / tax id: table cell first, geometric fallback ---
    vendor, address, tax_line = _attempt(
        extract_vendor_block, tables, default=(None, None, None)
    )
    if vendor:
        fields["vendor"] = found(vendor)
        fields["_vendor_address"] = found(address) if address else missing()
    else:
        # Fallback heuristic: only trusted when the document shows invoice
        # context (some amount field found), and always flagged ambiguous —
        # vendor names have no label on real invoices (exploration §5).
        vendor_guess = _attempt(_vendor_geometric, lines)
        has_context = False
        for label_list in (labels.SUBTOTAL_LABELS, labels.TOTAL_LABELS):
            result = _attempt(
                find_summary_amount, lines, label_list, default=(None, None, None)
            )
            if isinstance(result, tuple) and result[2] is not None:
                has_context = True
                break
        if vendor_guess and has_context:
            fields["vendor"] = ambiguous(
                vendor_guess, evidence="heuristic (no vendor table/label)"
            )
        else:
            fields["vendor"] = missing()
        fields["_vendor_address"] = missing()
    fields["vendor_tax_id"] = _as_field(_attempt(extract_tax_id, tax_line, lines))

    # --- labeled fields ---
    number = parse_invoice_number(find_labeled_value(lines, labels.INVOICE_NO_LABELS))
    fields["invoice_number"] = found(number) if number else missing()

    date_raw = find_labeled_value(lines, labels.INVOICE_DATE_LABELS)
    date_value, date_status = parse_date(date_raw)
    fields["invoice_date"] = (
        {"status": date_status, "value": date_value} if date_value else missing()
    )

    due_raw = find_labeled_value(lines, labels.DUE_DATE_LABELS)
    due_value, due_status = parse_date(due_raw)
    fields["due_date"] = (
        {"status": due_status, "value": due_value} if due_value else missing()
    )

    bill_to = extract_bill_to(lines)
    fields["bill_to"] = found(bill_to) if bill_to else missing()

    # --- totals ---
    subtotal_ctx, subtotal_val, subtotal = _attempt(
        find_summary_amount, lines, labels.SUBTOTAL_LABELS, default=(None, None, None)
    )
    fields["subtotal"] = (
        found(subtotal, raw=subtotal_val) if subtotal is not None else missing()
    )

    discount_ctx, discount_val, discount = _attempt(
        find_summary_amount, lines, labels.DISCOUNT_LABELS, default=(None, None, None)
    )
    fields["discount"] = (
        found(discount, raw=discount_val) if discount is not None else missing()
    )

    tax_ctx, tax_val, tax = _attempt(
        find_summary_amount, lines, labels.TAX_LABELS, default=(None, None, None)
    )
    fields["tax"] = found(tax, raw=tax_val) if tax is not None else missing()
    fields["tax_rate"] = _as_field(_attempt(extract_tax_rate, tax_ctx))

    total_ctx, total_val, total = _attempt(
        find_summary_amount, lines, labels.TOTAL_LABELS, default=(None, None, None)
    )
    fields["total"] = found(total, raw=total_val) if total is not None else missing()

    # --- currency: explicit label first (verified real layout: 'Currency:
    # INR' with plain-number amounts), then symbols + GST context ---
    label_value = find_labeled_value(lines, labels.CURRENCY_LABELS)
    label_code = label_value.strip().upper() if label_value else None
    if label_code and len(label_code) == 3 and label_code.isalpha():
        fields["currency"] = found(label_code, raw=label_value)
    elif label_value:
        fields["currency"] = ambiguous(
            None,
            evidence=(
                f"currency label present but value {label_value!r} is not a "
                "3-letter code — please confirm"
            ),
        )
    else:
        symbols = [
            detect_currency_symbol(value)
            for value in (subtotal_val, discount_val, tax_val, total_val)
            if value
        ]
        has_gst_context = (
            fields["vendor_tax_id"]["status"] == "found"
            or fields["tax"]["status"] == "found"
        )
        currency, status, evidence = resolve_currency(symbols, has_gst_context)
        if status == "missing":
            fields["currency"] = missing()
        elif status == "ambiguous":
            fields["currency"] = ambiguous(currency, evidence=evidence)
        else:
            fields["currency"] = found(currency)

    return fields


def _vendor_geometric(lines: list[str]) -> str | None:
    """Fallback heuristic: the vendor is the text before the first label on
    the top non-title line (real layouts print 'Vendor Name  Invoice No: X'),
    or the first plain line when no label is present. Skips titles, tax-id
    and bill-to lines. Caller flags the result ambiguous."""
    for line in lines[:8]:
        low = line.lower()
        if low in labels.DOC_TITLE_KEYWORDS:
            continue
        if _match_label(low, labels.VENDOR_TAX_ID_LABELS):
            continue
        if any(low.startswith(label) for label in labels.BILL_TO_LABELS):
            continue
        earliest = None
        for label_list in (labels.INVOICE_NO_LABELS, labels.INVOICE_DATE_LABELS):
            label = _match_label(low, label_list)
            if label is not None:
                position = low.find(label)
                if earliest is None or position < earliest:
                    earliest = position
        if earliest is not None:
            candidate = line[:earliest].strip()
        else:
            candidate = line
        if candidate and not candidate[0].isdigit():
            return candidate
    return None
