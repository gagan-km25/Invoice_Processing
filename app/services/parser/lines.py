"""Line-item extraction: locate the item table, separate items from summary
rows. Summary rows (Subtotal/Discount/Tax/Total — 2-cell rows) belong to the
header fields, never to the line items (exploration finding 4).
"""
import re

from .normalize import clean, parse_amount

_LINE_NO = re.compile(r"^\d{1,3}$")

# Summary-row labels (headerless layouts) — never line items.
_SUMMARY_LABEL_PREFIXES = (
    "subtotal", "discount", "cgst", "sgst", "igst", "gst", "total", "tax",
)


def find_item_table(tables):
    """The table whose header row mentions description + qty + price/amount."""
    for table in tables or []:
        if not table:
            continue
        for row in table:
            joined = " ".join(clean(cell).lower() for cell in row if cell)
            if (
                "description" in joined
                and ("qty" in joined or "quantity" in joined)
                and ("unit price" in joined or "price" in joined or "rate" in joined)
                and "amount" in joined
            ):
                return table
    return None


def extract_line_items(tables) -> tuple[list[dict], list[tuple[str, str]]]:
    """Return (items, summary_rows).

    items: rows whose leading cell is a line number, with a description and a
    parseable amount. Rows failing validation are dropped (E-15) — they are
    never silently guessed into shape.
    summary_rows: 2-cell (label, raw amount) rows for the totals strategies.
    Sprint E6: tables without a header row fall back to the headerless
    four-column layout (verified: CPS-INV-5099).
    """
    items: list[dict] = []
    summary_rows: list[tuple[str, str]] = []
    table = find_item_table(tables)
    if table is None:
        return _extract_headerless_four_column(tables)

    if table is None:
        return items, summary_rows  # no recognizable table → zero lines, no error (AC-2.3)

    for row in table:
        cells = [clean(cell) for cell in row]
        if not any(cells):
            continue
        non_empty = [c for c in cells if c]
        if len(non_empty) == 2 and not _LINE_NO.match(non_empty[0]):
            summary_rows.append((non_empty[0], non_empty[1]))
            continue
        if _LINE_NO.match(cells[0]) and len(cells) >= 5:
            description = cells[1]
            quantity = parse_amount(cells[2])
            unit_price = parse_amount(cells[3])
            amount = parse_amount(cells[4])
            if description and amount is not None:
                items.append(
                    {
                        "line_number": int(cells[0]),
                        "description": description,
                        "quantity": quantity,
                        "unit_price": unit_price,
                        "amount": amount,
                    }
                )
        elif (
            len(non_empty) == 4
            and cells[0]
            and not _LINE_NO.match(cells[0])
            and not _is_summary_label(cells[0])
        ):
            # Name-first four-column row (verified: CPS-INV-5099 — header row
            # present, item rows carry no line number):
            # [description, qty, unit price, amount]. Line numbers are
            # assigned 1..n; the header row itself is dropped because 'Qty'
            # does not parse as an amount (E-15).
            quantity = parse_amount(cells[1])
            unit_price = parse_amount(cells[2])
            amount = parse_amount(cells[3])
            if quantity is not None and amount is not None:
                items.append(
                    {
                        "line_number": len(items) + 1,
                        "description": cells[0],
                        "quantity": quantity,
                        "unit_price": unit_price,
                        "amount": amount,
                    }
                )
        # anything else (malformed rows) is dropped with no crash (E-15)
    return items, summary_rows


def _is_summary_label(text: str) -> bool:
    low = text.lower()
    return any(low.startswith(label) for label in _SUMMARY_LABEL_PREFIXES)


def _qualifies_headerless_item(cells: list[str]) -> bool:
    """A headerless four-column item row: [description, qty, unit price,
    amount] — description present and non-numeric (never a summary label or
    a line number), the remaining cells parseable amounts."""
    if len(cells) != 4 or not cells[0]:
        return False
    if _LINE_NO.match(cells[0]) or _is_summary_label(cells[0]):
        return False
    try:
        float(cells[0].replace(",", ""))
    except ValueError:
        pass
    else:
        return False  # description must not be a bare number
    return (
        parse_amount(cells[1]) is not None
        and parse_amount(cells[2]) is not None
        and parse_amount(cells[3]) is not None
    )


def _extract_headerless_four_column(tables):
    """Headerless four-column layout (verified: CPS-INV-5099): no header
    row; item rows are [description, qty, unit price, amount]; summary rows
    (Subtotal/GST/Total) carry leading empty cells and are kept out of the
    items — their totals reach the strategies via the text layer. Requires
    ≥2 item rows so unrelated tables are never guessed into items.
    Line numbers are assigned 1..n (the layout has none)."""
    for table in tables or []:
        rows = [[clean(c) for c in row] for row in table]
        rows = [row for row in rows if any(row)]
        qualifying = [row for row in rows if _qualifies_headerless_item(row)]
        if len(qualifying) < 2:
            continue  # totals-only or unrecognised — never fabricate items
        items = [
            {
                "line_number": number,
                "description": row[0],
                "quantity": parse_amount(row[1]),
                "unit_price": parse_amount(row[2]),
                "amount": parse_amount(row[3]),
            }
            for number, row in enumerate(qualifying, start=1)
        ]
        return items, []  # totals arrive via the text-layer strategies
    return [], []
