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
from decimal import Decimal

from . import currencies, labels
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


def _row_looks_like_items(row) -> bool:
    """A table row that carries a description plus two or more numeric or
    amount cells is a line-item row, not a vendor block (verified:
    SCS-INV-2614 — headerless item rows like 'Cloud hosting plan | 10 |
    n3,500.00 | n35,000.00' were accepted as the vendor)."""
    cells = [clean(c) for c in row if clean(c)]
    if len(cells) < 3 or parse_amount(cells[0]) is not None:
        return False
    amount_like = sum(1 for c in cells[1:] if parse_amount(c) is not None)
    return amount_like >= 2


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
        if _row_looks_like_items(table[0]):
            continue  # items table: leading cell is a line-item description
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


def _collect_tax_matches(lines: list[str]) -> list[tuple[str, str, str, Decimal]]:
    """Every tax-labelled summary row with a parseable amount:
    (context_line, matched label, raw value part, amount). Split-GST
    layouts list CGST/SGST/IGST components on separate rows (§6)."""
    matches: list[tuple[str, str, str, Decimal]] = []
    for line in lines:
        low = line.lower()
        if _match_label(low, labels.VENDOR_TAX_ID_LABELS):
            # vendor tax-identifier line ('Tax ID: …', 'GSTIN: …') — never a
            # tax amount (verified: SCS-INV-2614 tax became the GSTIN digits)
            continue
        label = _match_label(low, labels.TAX_LABELS)
        if label is None:
            continue
        rest = line[low.find(label) + len(label):].strip(" :")
        value_part = re.sub(r"\([^)]*%\)", " ", rest)
        amount = parse_amount(value_part)
        if amount is not None:
            matches.append((line, label, value_part, amount))
    return matches


def _resolve_tax(
    matches: list[tuple[str, str, str, Decimal]],
) -> tuple[str | None, str | None, Decimal | None]:
    """(context, raw value part, tax amount) for the invoice.

    Split-GST layouts (§6) list CGST/SGST/IGST components separately: the
    components are SUMMED. A combined GST/Tax/VAT row alongside components
    is never double-counted — the invoice's own combined tax row wins.
    A single row keeps the exact pre-existing behaviour."""
    if not matches:
        return None, None, None
    components = [m for m in matches if m[1] in ("cgst", "sgst", "igst")]
    combined = [m for m in matches if m[1] not in ("cgst", "sgst", "igst")]
    if components and not combined:
        total = sum((m[3] for m in components), Decimal("0.00"))
        return components[0][0], components[0][2], total.quantize(Decimal("0.01"))
    first = combined[0] if combined else matches[0]
    return first[0], first[2], first[3]


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

    tax_matches = _collect_tax_matches(lines)
    tax_ctx, tax_val, tax = _resolve_tax(tax_matches)
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
        if currencies.is_known_code(label_code):
            fields["currency"] = found(label_code, raw=label_value)
        else:
            fields["currency"] = ambiguous(
                label_code,
                evidence=(
                    f"{label_code!r} is not a known ISO 4217 code — "
                    "please confirm"
                ),
            )
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

    # Zero-decimal currencies (JPY, KRW, …) are not forced to two decimals:
    # requantize the headline amounts to the currency's minor-unit exponent
    # (Sprint E6, ISO 4217 dataset).
    # F1: normalization only on a CONFIRMED currency — an ambiguous value
    # (¥ = JPY or CNY; unknown ISO code) must not trigger requantization.
    resolved = None
    if fields["currency"].get("status") == "found":
        resolved = fields["currency"].get("value")
    exponent = currencies.exponent_for(resolved) if resolved else None
    if exponent is not None and exponent != 2:
        quantum = Decimal(1).scaleb(-exponent)
        for name in ("subtotal", "discount", "tax", "total"):
            field = fields.get(name)
            if isinstance(field, dict) and isinstance(field.get("value"), Decimal):
                field["value"] = field["value"].quantize(quantum)

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
