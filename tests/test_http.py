"""HTTP errors name the endpoint, keep a redacted body snippet, and are classified."""

import io
import urllib.error

import pytest

from swing.data.errors import VendorError, fix_line, kind_of
from swing.data.http import get_json


class _Opener:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def open(self, request, timeout):  # noqa: ANN001
        raise self._error


def _http_error(url: str, status: int, body: bytes) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, status, "Forbidden", {}, io.BytesIO(body))


@pytest.mark.parametrize(
    ("status", "kind"),
    [(401, "invalid_key"), (403, "plan_forbidden"), (429, "rate_limited"), (500, "upstream"), (503, "upstream")],
)
def test_status_classes_and_endpoint_in_the_error(monkeypatch, status: int, kind: str):
    url = "https://finnhub.io/api/v1/calendar/earnings?symbol=AAPL&token=sk-live-1234"
    body = b'{"error":"You don\'t have access to this resource. key sk-live-1234"}'
    monkeypatch.setattr("urllib.request.build_opener", lambda *_a: _Opener(_http_error(url, status, body)))
    with pytest.raises(VendorError) as caught:
        get_json(url, {"X-Finnhub-Token": "sk-live-1234"})
    error = caught.value
    assert error.kind == kind
    assert error.status == status
    assert error.endpoint == "/api/v1/calendar/earnings"
    text = str(error)
    assert text.startswith(f"/api/v1/calendar/earnings:http_{status}:{kind}:")
    assert "You don't have access to this resource." in text
    assert "sk-live-1234" not in text
    assert kind_of(f"vendor_error:finnhub:{text}") == kind


def test_body_snippet_is_capped_at_200_characters(monkeypatch):
    url = "https://api.massive.com/v2/aggs/grouped"
    monkeypatch.setattr(
        "urllib.request.build_opener", lambda *_a: _Opener(_http_error(url, 403, b"x" * 5000))
    )
    with pytest.raises(VendorError) as caught:
        get_json(url, {"Authorization": "Bearer abcd1234"})
    assert len(caught.value.detail) <= 200


def test_bearer_token_is_redacted_from_the_body(monkeypatch):
    url = "https://api.massive.com/v2/aggs/grouped"
    body = b'{"message":"bad key abcd1234"}'
    monkeypatch.setattr("urllib.request.build_opener", lambda *_a: _Opener(_http_error(url, 401, body)))
    with pytest.raises(VendorError) as caught:
        get_json(url, {"Authorization": "Bearer abcd1234"})
    assert "abcd1234" not in str(caught.value)
    assert caught.value.kind == "invalid_key"


def test_timeouts_are_upstream(monkeypatch):
    url = "https://finnhub.io/api/v1/calendar/earnings"
    monkeypatch.setattr("urllib.request.build_opener", lambda *_a: _Opener(TimeoutError("timed out")))
    with pytest.raises(VendorError) as caught:
        get_json(url, {})
    assert caught.value.kind == "upstream"
    assert caught.value.endpoint == "/api/v1/calendar/earnings"


def test_every_kind_has_a_fix_line():
    for kind in ("missing_key", "invalid_key", "plan_forbidden", "rate_limited", "upstream", "bad_payload"):
        assert fix_line(kind, "FINNHUB_API_KEY")
    assert "FINNHUB_API_KEY" in fix_line("missing_key", "FINNHUB_API_KEY")
    assert kind_of("missing_api_key:FINNHUB_API_KEY") == "missing_key"
