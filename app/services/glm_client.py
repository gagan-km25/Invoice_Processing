"""GLM (Z.ai) chat-completions client — Sprint E2.

Thin transport only: builds the request, posts it, and returns the raw
assistant message content as a string. Prompt construction, response
validation, and retry policy live in `app/services/extraction.py` and the
pipeline.

Failure model (verified against docs.z.ai, 2026-10-12):
- `GlmTransient` — timeout / connection failure / HTTP 5xx / 429: worth a
  bounded retry (the pipeline's M1 allowance covers it).
- `GlmPermanent` — HTTP 4xx, non-JSON envelope, unexpected envelope shape:
  re-running cannot succeed.

Safety: the API key travels only in the Authorization header built here and
is never written to logs, exceptions, or the database. Provider response
bodies are never embedded in exception messages — only the HTTP status
code. `http_post_json` is the single seam tests stub (the suite never
touches the network).
"""
import requests


class GlmTransient(Exception):
    """Transient provider/transport failure — a bounded retry may succeed."""


class GlmPermanent(Exception):
    """Permanent provider failure — re-running cannot succeed."""


def http_post_json(url: str, *, headers: dict, payload: dict, timeout: float):
    """Single network seam (module-level so tests can stub it)."""
    return requests.post(url, headers=headers, json=payload, timeout=timeout)


def _headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def post_chat(
    *,
    api_key: str,
    base_url: str,
    model: str,
    messages: list[dict],
    json_mode: bool = False,
    timeout: float = 60.0,
    max_tokens: int | None = None,
) -> str:
    """One chat completion; returns the assistant message content.

    Raises GlmTransient for transport/timeout/5xx/429 and GlmPermanent for
    4xx or malformed envelopes. Exception messages never contain the key or
    provider bodies.
    """
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "stream": False,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    url = base_url.rstrip("/") + "/chat/completions"
    try:
        response = http_post_json(
            url,
            headers=_headers(api_key),
            payload=payload,
            timeout=timeout,
        )
    except GlmTransient:
        raise
    except requests.exceptions.RequestException as exc:
        # transport layer only (timeout, connection, TLS) — anything else is
        # a code defect and must not be misclassified as transient
        raise GlmTransient(
            f"the AI service could not be reached ({type(exc).__name__})"
        ) from None

    if response.status_code == 429 or response.status_code >= 500:
        raise GlmTransient(f"the AI service is unavailable (HTTP {response.status_code})")
    if response.status_code != 200:
        raise GlmPermanent(f"the AI service rejected the request (HTTP {response.status_code})")

    try:
        data = response.json()
        content = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise GlmPermanent(
            "the AI service returned a malformed response envelope"
        ) from None
    if not isinstance(content, str):
        raise GlmPermanent("the AI service returned a malformed response envelope")
    return content
