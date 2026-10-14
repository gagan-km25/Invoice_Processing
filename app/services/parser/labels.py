"""Label dictionaries and preference orders for field identification.

Preference orders matter: multiple 'total-like' labels appear on real invoices,
so the first label that yields a value wins, in this order (exploration §6,
E-11).
"""

DOC_TITLE_KEYWORDS = {"invoice", "tax invoice", "invoice cum bill", "bill"}

INVOICE_NO_LABELS = [
    "invoice no",
    "invoice no.",
    "invoice #",
    "invoice number",
    "invoice num",
    "ref no",
    "reference no",
]

INVOICE_DATE_LABELS = [
    "invoice date",
    "date of issue",
    "issue date",
    "date",
]

DUE_DATE_LABELS = [
    "due date",
    "payment due date",
    "payment due",
    "due by",
]

# NOTE: deliberately no 'due on' — 'Payment: Due on receipt' must not parse as
# a due date (exploration finding 3).

BILL_TO_LABELS = [
    "bill to",
    "billed to",
    "sold to",
    "customer",
    "invoice to",
]

VENDOR_TAX_ID_LABELS = [
    "gstin",
    "gst no",
    "gst reg no",
    "vat no",
    "vat id",
    "tax id",
    "tax no",
    "abn",
    "ein",
]

SUBTOTAL_LABELS = [
    "sub total",
    "subtotal",
    "sub-total",
    "net amount",
]

DISCOUNT_LABELS = [
    "discount",
    "disc",
]

TAX_LABELS = [
    "gst",
    "vat",
    "sales tax",
    "tax amount",
    "tax",
]

# Preference order — most specific first (E-11: 'Subtotal … Total … Grand Total').
TOTAL_LABELS = [
    "grand total",
    "total due",
    "amount due",
    "balance due",
    "invoice total",
    "total amount",
    "total",
]

# A line starting like this is the item-table header — stops bill-to capture.
ITEM_HEADER_PREFIXES = ("#",)

ITEM_HEADER_KEYWORDS = ("description", "qty", "unit price", "amount")

# Explicit currency label (e.g. "Currency: INR") — verified real layout
# (CPS-INV-5099) prints plain-number amounts with no glyph, plus this label.
CURRENCY_LABELS = ("currency code", "currency")

GST_CONTEXT_PATTERN = "gstin"
