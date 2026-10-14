"""Extraction service — Sprint E2: GLM (Z.ai) extraction with local fallback.

Provider selection (approved decision, P-E-16):
- `ZAI_API_KEY` configured → GLM for everything: text-layer PDFs via the
  text model (native JSON mode), images and scanned PDFs via the vision
  model on pypdfium2-rasterized pages (≤ `VISION_MAX_PAGES` pages).
- Unconfigured → the existing local rules parser for text PDFs; images and
  scans fail permanently with a clear "not configured" message (they require
  GLM — decision 1).
- Configured-GLM failures are NEVER silently swapped for the local parser
  (decision 3): they surface as typed failures the pipeline retries
  (`ExtractionRetryable`) or terminates (`ExtractionPermanent`), always with
  a user-safe message and the raw provider response retained locally.

This module never writes `invoices.status` — the pipeline owns transitions.
The API key lives only in the client call; provider bodies never appear in
exception messages or logs (applog allowlist).
"""
import base64
import io
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pdfplumber
import pypdfium2 as pdfium
from flask import current_app

from app.db import get_db
from app.db.repository import get_invoice, update_extraction
from app.services import glm_client, parser


class ExtractionError(Exception):
    """Base: extraction failed. `user_message` is always user-safe."""

    def __init__(self, user_message: str, raw_response: str | None = None):
        self.user_message = user_message
        self.raw_response = raw_response
        super().__init__(user_message)


class ExtractionPermanent(ExtractionError):
    """Re-running extraction cannot succeed."""


class ExtractionRetryable(ExtractionError):
    """Transient condition — a bounded retry may succeed."""


# --------------------------------------------------------------------------
# AI response schema/validation
# --------------------------------------------------------------------------

_TEXT_FIELDS = (
    "vendor", "vendor_tax_id", "invoice_number", "bill_to",
    # Enhancement §6 extended fields (Sprint E3):
    "po_number", "bill_to_address", "ship_to_name", "ship_to_address",
)
_AMOUNT_FIELDS = ("subtotal", "discount", "tax", "total", "tax_rate")
_DATE_FIELDS = ("invoice_date", "due_date")

_REASK_INSTRUCTION = (
    "Your previous response was not valid JSON matching the schema. "
    "Respond again with ONLY the JSON object — no markdown fences, no "
    "commentary."
)

_NO_KEY_IMAGE_MESSAGE = (
    "AI extraction is not configured — images and scanned documents require "
    "the GLM vision model. Set ZAI_API_KEY to enable it."
)
_NO_KEY_SCAN_MESSAGE = (
    "The PDF contains no selectable text — it is likely a scan. Scanned "
    "documents require AI extraction, which is not configured "
    "(set ZAI_API_KEY to enable it)."
)
_INVALID_AI_MESSAGE = (
    "The AI service returned a response that could not be parsed as valid "
    "invoice data."
)


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        lines = [line for line in lines if not line.strip().startswith("```")]
        stripped = "\n".join(lines).strip()
    return stripped


def _coerce_text(value):
    """str → stripped str (or None); anything else → (None, note)."""
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, "not a string"
    cleaned = value.strip()
    return (cleaned or None), None


def _coerce_amount(value):
    if value is None:
        return None, None
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None, "not a number"
    if not amount.is_finite():
        return None, "not a number"
    return amount.quantize(Decimal("0.01")), None


def _coerce_date(value):
    if value is None:
        return None, None
    try:
        parsed = datetime.strptime(str(value).strip(), "%Y-%m-%d")
    except ValueError:
        return None, "not a YYYY-MM-DD date"
    return parsed.date().isoformat(), None


def _found(value):
    return {"status": "found", "value": value}


def _missing(note=None):
    return {"status": "missing", **({"note": note} if note else {})}


def ai_json_to_draft(content: str, model: str, page_count: int | None) -> dict:
    """Convert a GLM response to a parser-shaped draft.

    Raises ValueError when the content is not valid JSON or not an object
    with the expected top-level shape (the caller may re-ask once). Field
    values that are present but malformed degrade to `missing` with a note
    (never crash, never store raw strings in numeric columns).
    """
    text = _strip_code_fences(content)
    try:
        obj = json.loads(text)
    except ValueError:
        raise ValueError("not valid JSON") from None
    if not isinstance(obj, dict):
        raise ValueError("not a JSON object")

    fields = {}
    for name in _TEXT_FIELDS:
        value, note = _coerce_text(obj.get(name))
        fields[name] = _found(value) if value is not None else _missing(note)
        if note:
            fields[name]["note"] = note

    currency, note = _coerce_text(obj.get("currency"))
    if currency is not None and len(currency) != 3:
        currency, note = None, "not a 3-letter code"
    if currency is not None:
        currency = currency.upper()
    fields["currency"] = _found(currency) if currency else _missing(note)
    if note:
        fields["currency"]["note"] = note

    for name in _DATE_FIELDS:
        value, note = _coerce_date(obj.get(name))
        fields[name] = _found(value) if value is not None else _missing(note)
        if note:
            fields[name]["note"] = note

    for name in _AMOUNT_FIELDS:
        value, note = _coerce_amount(obj.get(name))
        fields[name] = _found(value) if value is not None else _missing(note)
        if note:
            fields[name]["note"] = note

    raw_lines = obj.get("line_items", [])
    if raw_lines is None:
        raw_lines = []
    if not isinstance(raw_lines, list):
        raise ValueError("line_items must be an array")

    lines = []
    for item in raw_lines:
        if not isinstance(item, dict):
            continue
        description, note = _coerce_text(item.get("description"))
        if description is None:
            continue
        quantity, note_q = _coerce_amount(item.get("quantity"))
        unit_price, note_u = _coerce_amount(item.get("unit_price"))
        amount, note_a = _coerce_amount(item.get("amount"))
        line_tax, note_t = _coerce_amount(item.get("tax"))
        if None in (quantity, unit_price, amount):
            continue
        lines.append(
            {
                "line_number": len(lines) + 1,
                "description": description,
                "quantity": quantity,
                "unit_price": unit_price,
                "amount": amount,
                # Optional per-line tax (enhancement §6): absent/invalid → None
                "tax": line_tax,
            }
        )

    return {
        "fields": fields,
        "lines": lines,
        "checks": [],
        "meta": {
            "page_count": page_count,
            "parser_version": 1,
            "model": model,
            "source": "glm",
        },
    }


def _cap_raw(text: str, limit: int) -> str:
    data = text.encode("utf-8")
    if len(data) <= limit:
        return text
    return data[:limit].decode("utf-8", errors="ignore") + "\n…[truncated]"


# --------------------------------------------------------------------------
# Prompt construction
# --------------------------------------------------------------------------

_RESPONSE_SCHEMA_HINT = (
    '{"invoice_number": string|null, "invoice_date": "YYYY-MM-DD"|null, '
    '"due_date": "YYYY-MM-DD"|null, "vendor": string|null, '
    '"vendor_tax_id": string|null, "bill_to": string|null, '
    '"bill_to_address": string|null, "ship_to_name": string|null, '
    '"ship_to_address": string|null, "po_number": string|null, '
    '"currency": string|null (ISO 3-letter code), "subtotal": number|null, '
    '"discount": number|null, "tax": number|null, "tax_rate": number|null, '
    '"total": number|null, "line_items": array of {"description": string, '
    '"quantity": number, "unit_price": number, "amount": number, '
    '"tax": number|null}}'
)

_SYSTEM_PROMPT = (
    "You are an invoice information extraction service. Extract the requested "
    "fields from the invoice and respond with ONLY a JSON object matching this "
    "schema — no markdown fences, no commentary. Amounts must be plain numbers "
    "without currency symbols or thousands separators. Use null for values "
    "that are not present. Schema: " + _RESPONSE_SCHEMA_HINT
)


def _glm_chat(
    api_key: str, messages: list[dict], *, json_mode: bool, model: str,
) -> str:
    """One GLM call with provider errors mapped to extraction's typed
    failures (transient → the pipeline's retry allowance; permanent →
    visible terminal failure — decision 3, no local-parser fallback)."""
    config = current_app.config
    try:
        return glm_client.post_chat(
            api_key=api_key,
            base_url=config["ZAI_BASE_URL"],
            model=model,
            messages=messages,
            json_mode=json_mode,
            timeout=config["ZAI_TIMEOUT_SECONDS"],
            max_tokens=config["ZAI_MAX_TOKENS"],
        )
    except glm_client.GlmTransient as exc:
        raise ExtractionRetryable(str(exc)) from None
    except glm_client.GlmPermanent as exc:
        raise ExtractionPermanent(str(exc)) from None


def _glm_extract_with_reask(
    api_key: str, messages: list[dict], *, json_mode: bool, model: str,
    page_count: int | None,
) -> tuple[dict, str]:
    """One extraction call; a single re-ask when the response is not valid
    JSON/shape. Returns (draft, capped_raw). Raises ExtractionPermanent with
    the raw response attached when both attempts are unusable."""
    limit = current_app.config["RAW_RESPONSE_MAX_BYTES"]
    content = _glm_chat(api_key, messages, json_mode=json_mode, model=model)
    try:
        return ai_json_to_draft(content, model, page_count), _cap_raw(content, limit)
    except ValueError:
        pass
    retry_messages = messages + [
        {"role": "assistant", "content": content[:4000]},
        {"role": "user", "content": _REASK_INSTRUCTION},
    ]
    content = _glm_chat(api_key, retry_messages, json_mode=json_mode, model=model)
    capped = _cap_raw(content, limit)
    try:
        draft = ai_json_to_draft(content, model, page_count)
    except ValueError:
        raise ExtractionPermanent(_INVALID_AI_MESSAGE, raw_response=capped) from None
    return draft, capped


def _glm_text_draft(api_key: str, invoice_text: str, page_count: int):
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Invoice text:\n\n{invoice_text}\n\nRespond with only the JSON object.",
        },
    ]
    model = current_app.config["ZAI_TEXT_MODEL"]
    return _glm_extract_with_reask(
        api_key, messages, json_mode=True, model=model, page_count=page_count
    )


def _glm_vision_draft(api_key: str, images_b64: list[str], page_count: int | None):
    content_parts = [
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
        for b64 in images_b64
    ]
    content_parts.append(
        {
            "type": "text",
            "text": _SYSTEM_PROMPT
            + "\n\nExtract the invoice fields from the attached scanned "
            "invoice page image(s). Respond with only the JSON object.",
        }
    )
    messages = [{"role": "user", "content": content_parts}]
    model = current_app.config["ZAI_VISION_MODEL"]
    return _glm_extract_with_reask(
        api_key, messages, json_mode=False, model=model, page_count=page_count
    )


# --------------------------------------------------------------------------
# Vision helpers
# --------------------------------------------------------------------------

_VISION_IMAGE_MAX_BYTES = 5 * 1024 * 1024
_VISION_IMAGE_MAX_PIXELS = 6000


def _rasterize_pdf(data: bytes, max_pages: int) -> list[str]:
    """Rasterize at most `max_pages` pages to base64 PNGs (pypdfium2),
    downscaling any page above the provider's 6000 px limit."""
    images_b64: list[str] = []
    doc = pdfium.PdfDocument(io.BytesIO(data))
    try:
        for index in range(min(len(doc), max_pages)):
            page = doc[index]
            scale = 2.0
            image = page.render(scale=scale).to_pil()
            while max(image.size) > _VISION_IMAGE_MAX_PIXELS and scale > 0.5:
                scale /= 2
                image = page.render(scale=scale).to_pil()
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            images_b64.append(base64.b64encode(buf.getvalue()).decode("ascii"))
    finally:
        doc.close()
    return images_b64


# --------------------------------------------------------------------------
# Entry point (pipeline seam — unchanged signature)
# --------------------------------------------------------------------------

def extract_stored_invoice(invoice_id: int) -> tuple[bool, str]:
    """Run extraction for a stored upload and persist the draft.

    Never writes `invoices.status`. Never raises on a bad file: failures are
    typed (ExtractionRetryable / ExtractionPermanent) with user-safe
    messages; the raw provider response (when any) is size-capped and stored
    locally for traceability.
    """
    config = current_app.config
    api_key = config["ZAI_API_KEY"]

    conn = get_db()
    try:
        record = get_invoice(conn, invoice_id)
    finally:
        conn.close()
    if record is None:
        raise ExtractionPermanent(f"Record #{invoice_id} could not be found.")
    if record["status"] == "failed" and not record["stored_filename"]:
        raise ExtractionPermanent(record["error_message"] or "previous failure")

    file_path = Path(current_app.config["UPLOAD_DIR"]) / record["stored_filename"]
    try:
        data = file_path.read_bytes()
    except OSError:
        raise ExtractionRetryable(
            "The stored file could not be read right now."
        ) from None

    file_type = record["file_type"] or "pdf"

    # ---- image uploads always require GLM vision -------------------------
    if file_type == "image":
        if not api_key:
            raise ExtractionPermanent(_NO_KEY_IMAGE_MESSAGE)
        if len(data) > _VISION_IMAGE_MAX_BYTES:
            raise ExtractionPermanent(
                "The image is too large for vision extraction (max 5 MB)."
            )
        draft, raw = _glm_vision_draft(
            api_key, [base64.b64encode(data).decode("ascii")], page_count=1
        )
        found = _persist_draft(invoice_id, draft, raw)
        return (
            True,
            f"GLM vision extraction complete: {found} fields found, "
            f"{len(draft['lines'])} line items",
        )

    # ---- PDF: text layer first, scans via vision --------------------------
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            page_count = len(pdf.pages)
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            tables = [
                table
                for page in pdf.pages
                for table in (page.extract_tables() or [])
            ]
    except ExtractionPermanent:
        raise
    except Exception:
        raise ExtractionPermanent(
            "The file could not be processed — it may be corrupt."
        ) from None

    if len(text.strip()) < 20:
        # Scanned PDF: vision model required (configured) or clear failure.
        if not api_key:
            raise ExtractionPermanent(_NO_KEY_SCAN_MESSAGE)
        try:
            images_b64 = _rasterize_pdf(data, config["VISION_MAX_PAGES"])
        except ExtractionPermanent:
            raise
        except Exception as exc:
            # pdfium cannot render this PDF (structurally valid but
            # unrenderable) — a permanent, user-safe failure, never a
            # generic crash (review M-A).
            raise ExtractionPermanent(
                "The scanned PDF could not be converted for vision "
                "extraction — it may be corrupt or use unsupported PDF "
                "features."
            ) from None
        draft, raw = _glm_vision_draft(api_key, images_b64, page_count=page_count)
        found = _persist_draft(invoice_id, draft, raw)
        return (
            True,
            f"GLM vision extraction complete: {found} fields found, "
            f"{len(draft['lines'])} line items",
        )

    # Text-layer PDF: GLM when configured, local rules parser otherwise.
    if api_key:
        draft, raw = _glm_text_draft(api_key, text, page_count)
        found = _persist_draft(invoice_id, draft, raw)
        return (
            True,
            f"GLM extraction complete: {found} of {len(draft['fields'])} "
            f"fields found, {len(draft['lines'])} line items",
        )

    draft = parser.parse(text, tables, page_count=page_count)
    _persist_local_draft(invoice_id, draft)
    found = sum(
        1
        for field in draft["fields"].values()
        if field["status"] in ("found", "ambiguous")
    )
    return (
        True,
        f"{found} of {len(draft['fields'])} fields found, "
        f"{len(draft['lines'])} line items",
    )


def _persist_draft(invoice_id: int, draft: dict, raw: str) -> int:
    capped = _cap_raw(raw, current_app.config["RAW_RESPONSE_MAX_BYTES"])
    conn = get_db()
    try:
        update_extraction(
            conn, invoice_id, draft=draft, raw_response=capped, write_lines=True
        )
    finally:
        conn.close()
    return sum(
        1
        for field in draft["fields"].values()
        if field["status"] in ("found", "ambiguous")
    )


def _persist_local_draft(invoice_id: int, draft: dict) -> None:
    conn = get_db()
    try:
        # A local-parser run clears any stale GLM raw response (review L-B):
        # the retained raw must always match the extraction source.
        update_extraction(
            conn, invoice_id, draft=draft, clear_raw_response=True
        )
    finally:
        conn.close()
