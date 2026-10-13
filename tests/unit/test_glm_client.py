"""Sprint E2 unit tests — GLM client transport and error classification.

The network seam (`glm_client.http_post_json`) is stubbed; nothing here
touches the network. The API key is a fake sentinel.
"""
import pytest
import requests

from app.services import glm_client


class _FakeResponse:
    def __init__(self, status_code, payload=None, raise_json=False):
        self.status_code = status_code
        self._payload = payload
        self._raise_json = raise_json

    def json(self):
        if self._raise_json:
            raise ValueError("not json")
        return self._payload


def _stub(monkeypatch, responder):
    calls = []

    def fake_post(url, *, headers, payload, timeout):
        calls.append(
            {"url": url, "headers": headers, "payload": payload, "timeout": timeout}
        )
        return responder

    monkeypatch.setattr(glm_client, "http_post_json", fake_post)
    return calls


def test_post_chat_returns_content_and_builds_request(monkeypatch):
    calls = _stub(
        monkeypatch, _FakeResponse(200, {"choices": [{"message": {"content": "{}"}}]})
    )
    content = glm_client.post_chat(
        api_key="sentinel-key",
        base_url="https://api.example/v4/",
        model="glm-test",
        messages=[{"role": "user", "content": "hi"}],
        json_mode=True,
        timeout=5,
    )
    assert content == "{}"
    assert calls[0]["url"] == "https://api.example/v4/chat/completions"
    assert calls[0]["headers"]["Authorization"] == "Bearer sentinel-key"
    assert calls[0]["payload"]["model"] == "glm-test"
    assert calls[0]["payload"]["response_format"] == {"type": "json_object"}
    assert calls[0]["timeout"] == 5


def test_post_chat_json_mode_off_omits_response_format(monkeypatch):
    calls = _stub(
        monkeypatch, _FakeResponse(200, {"choices": [{"message": {"content": "{}"}}]})
    )
    glm_client.post_chat(
        api_key="k",
        base_url="https://api.example/v4/",
        model="m",
        messages=[{"role": "user", "content": "hi"}],
        json_mode=False,
    )
    assert "response_format" not in calls[0]["payload"]


def test_max_tokens_included_when_provided(monkeypatch):
    """M-B — the configured output cap travels in the request payload."""
    calls = _stub(
        monkeypatch, _FakeResponse(200, {"choices": [{"message": {"content": "{}"}}]})
    )
    glm_client.post_chat(
        api_key="k",
        base_url="https://api.example/v4/",
        model="m",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=4000,
    )
    assert calls[0]["payload"]["max_tokens"] == 4000


def test_max_tokens_omitted_when_none(monkeypatch):
    calls = _stub(
        monkeypatch, _FakeResponse(200, {"choices": [{"message": {"content": "{}"}}]})
    )
    glm_client.post_chat(
        api_key="k",
        base_url="https://api.example/v4/",
        model="m",
        messages=[{"role": "user", "content": "hi"}],
    )
    assert "max_tokens" not in calls[0]["payload"]


def test_non_request_transport_error_is_not_transient(monkeypatch):
    """L-C — only RequestException subclasses are transient; a code defect
    (arbitrary exception from the transport seam) propagates unchanged."""
    def not_a_request_error(url, *, headers, payload, timeout):
        raise ValueError("a code defect, not a transport problem")

    monkeypatch.setattr(glm_client, "http_post_json", not_a_request_error)
    with pytest.raises(ValueError, match="code defect"):
        glm_client.post_chat(
            api_key="k",
            base_url="https://x/v4/",
            model="m",
            messages=[{"role": "user", "content": "hi"}],
        )


@pytest.mark.parametrize("status", [429, 500, 502, 503])
def test_http_5xx_and_429_are_transient(monkeypatch, status):
    _stub(monkeypatch, _FakeResponse(status, {"choices": []}))
    with pytest.raises(glm_client.GlmTransient) as excinfo:
        glm_client.post_chat(
            api_key="k", base_url="https://x/v4/", model="m",
            messages=[{"role": "user", "content": "hi"}],
        )
    assert f"HTTP {status}" in str(excinfo.value)


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_http_4xx_are_permanent(monkeypatch, status):
    _stub(monkeypatch, _FakeResponse(status, {"error": {"message": "sentinel-body"}}))
    with pytest.raises(glm_client.GlmPermanent) as excinfo:
        glm_client.post_chat(
            api_key="k", base_url="https://x/v4/", model="m",
            messages=[{"role": "user", "content": "hi"}],
        )
    # provider bodies never enter the exception message
    assert "sentinel-body" not in str(excinfo.value)
    assert f"HTTP {status}" in str(excinfo.value)


def test_timeout_is_transient(monkeypatch):
    def raise_timeout(url, *, headers, payload, timeout):
        raise requests.exceptions.Timeout("timed out")

    _stub_via = monkeypatch.setattr(glm_client, "http_post_json", raise_timeout)
    with pytest.raises(glm_client.GlmTransient):
        glm_client.post_chat(
            api_key="k", base_url="https://x/v4/", model="m",
            messages=[{"role": "user", "content": "hi"}],
        )


def test_connection_error_is_transient(monkeypatch):
    def raise_connection(url, *, headers, payload, timeout):
        raise requests.exceptions.ConnectionError("no route")

    monkeypatch.setattr(glm_client, "http_post_json", raise_connection)
    with pytest.raises(glm_client.GlmTransient) as excinfo:
        glm_client.post_chat(
            api_key="k", base_url="https://x/v4/", model="m",
            messages=[{"role": "user", "content": "hi"}],
        )
    assert "ConnectionError" in str(excinfo.value)


def test_malformed_envelope_is_permanent(monkeypatch):
    _stub(monkeypatch, _FakeResponse(200, {"unexpected": True}, raise_json=False))
    with pytest.raises(glm_client.GlmPermanent):
        glm_client.post_chat(
            api_key="k", base_url="https://x/v4/", model="m",
            messages=[{"role": "user", "content": "hi"}],
        )


def test_non_json_envelope_is_permanent(monkeypatch):
    _stub(monkeypatch, _FakeResponse(200, raise_json=True))
    with pytest.raises(glm_client.GlmPermanent):
        glm_client.post_chat(
            api_key="k", base_url="https://x/v4/", model="m",
            messages=[{"role": "user", "content": "hi"}],
        )
