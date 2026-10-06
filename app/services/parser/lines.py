"""Line-item extraction: locate the item table, separate items from summary
rows. Summary rows (Subtotal/Discount/Tax/Total — 2-cell rows) belong to the
header fields, never to the line items (exploration finding 4).
"""
import re

from .normalize import clean, parse_amount

_LINE_NO = re.compile(r"^\d{1,3}$")


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
    """
    items: list[dict] = []
    summary_rows: list[tuple[str, str]] = []
    table = find_item_table(tables)

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
        # anything else (malformed rows) is dropped with no crash (E-15)
    return items, summary_rows
