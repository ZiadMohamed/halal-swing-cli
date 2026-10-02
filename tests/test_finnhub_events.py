"""Finnhub supplies the earnings calendar only (free tier), never OHLC or dividends."""

import json
from datetime import date
from pathlib import Path

import pytest

from swing.data.errors import MissingApiKeyError, VendorError
from swing.data.finnhub import FinnhubEvents

_FIXTURES = Path("tests/fixtures")


def _payload(name: str):
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def test_recorded_earnings_calendar_uses_the_free_window():
    urls: list[str] = []

    def transport(url: str, headers: dict[str, str]):
        urls.append(url)
        assert headers["X-Finnhub-Token"] == "fh-secret"
        assert "fh-secret" not in url
        return _payload("finnhub_earnings.json")

    events = FinnhubEvents(api_key="fh-secret", transport=transport, today=date(2026, 10, 1))
    earnings = events.earnings_calendar("aapl")
    assert len(earnings) == 1
    assert earnings[0].ticker == "AAPL"
    assert earnings[0].report_date == date(2026, 10, 29)
    assert earnings[0].hour == "amc"
    assert earnings[0].quarter == 4
    assert earnings[0].year == 2026
    assert earnings[0].source == "finnhub"
    assert len(urls) == 1
    assert "/calendar/earnings" in urls[0]
    assert "from=2026-09-26" in urls[0]
    assert "to=2026-11-05" in urls[0]


def test_finnhub_has_no_dividend_or_candle_requests():
    assert not hasattr(FinnhubEvents, "dividend_calendar")
    source = Path("src/swing/data/finnhub.py").read_text(encoding="utf-8")
    assert "/stock/" not in source


def test_missing_finnhub_key_is_a_typed_error_before_any_request():
    def transport(url: str, headers: dict[str, str]):
        raise AssertionError("network")

    events = FinnhubEvents(api_key="", transport=transport, today=date(2026, 10, 1))
    with pytest.raises(MissingApiKeyError) as caught:
        events.earnings_calendar("AAPL")
    assert caught.value.env_name == "FINNHUB_API_KEY"
    assert caught.value.code == "missing_api_key"


@pytest.mark.parametrize(
    ("status", "kind"),
    [(401, "invalid_key"), (403, "plan_forbidden"), (429, "rate_limited"), (502, "upstream")],
)
def test_http_failures_keep_the_endpoint_status_and_class(status: int, kind: str):
    def transport(url: str, headers: dict[str, str]):
        raise VendorError("fh-secret said no", kind=kind, endpoint="/api/v1/calendar/earnings", status=status)

    events = FinnhubEvents(api_key="fh-secret", transport=transport, today=date(2026, 10, 1))
    with pytest.raises(VendorError) as caught:
        events.earnings_calendar("AAPL")
    text = str(caught.value)
    assert "/calendar/earnings" in text
    assert f"http_{status}" in text
    assert kind in text
    assert "fh-secret" not in text
    assert caught.value.kind == kind


def test_an_error_field_in_a_200_body_is_a_bad_payload_with_the_endpoint():
    def transport(url: str, headers: dict[str, str]):
        return {"error": "You don't have access to this resource."}

    events = FinnhubEvents(api_key="fh-secret", transport=transport, today=date(2026, 10, 1))
    with pytest.raises(VendorError) as caught:
        events.earnings_calendar("AAPL")
    assert caught.value.kind == "bad_payload"
    assert "/calendar/earnings" in str(caught.value)
