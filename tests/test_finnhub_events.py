"""Finnhub supplies earnings and dividend calendars, never OHLC."""

import json
from datetime import date
from pathlib import Path

import pytest

from swing.data.errors import MissingApiKeyError
from swing.data.finnhub import FinnhubEvents

_FIXTURES = Path("tests/fixtures")


def _payload(name: str):
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def test_recorded_calendars_are_shaped_for_blackout_and_ex_div_rules():
    urls: list[str] = []

    def transport(url: str, headers: dict[str, str]):
        urls.append(url)
        assert headers["X-Finnhub-Token"] == "fh-secret"
        assert "fh-secret" not in url
        assert "candle" not in url
        if "/calendar/earnings" in url:
            assert "symbol=AAPL" in url
            return _payload("finnhub_earnings.json")
        if "/stock/dividend" in url:
            assert "symbol=AAPL" in url
            return _payload("finnhub_dividends.json")
        raise AssertionError(url)

    events = FinnhubEvents(api_key="fh-secret", transport=transport, today=date(2026, 10, 1))
    earnings = events.earnings_calendar("aapl")
    dividends = events.dividend_calendar("AAPL")
    assert len(earnings) == 1
    assert earnings[0].ticker == "AAPL"
    assert earnings[0].report_date == date(2026, 10, 29)
    assert earnings[0].hour == "amc"
    assert earnings[0].quarter == 4
    assert earnings[0].year == 2026
    assert dividends[0].ex_date == date(2026, 11, 6)
    assert dividends[0].amount == 0.26
    assert dividends[0].currency == "USD"
    assert dividends[0].pay_date == date(2026, 11, 13)
    assert all("/stock/candle" not in url for url in urls)


def test_wrapped_dividend_payload_is_accepted():
    def transport(url: str, headers: dict[str, str]):
        if "/stock/dividend" in url:
            return {"data": [{"symbol": "AAPL", "date": "2026-11-06", "amount": 0.25, "currency": "USD"}]}
        return {"earningsCalendar": []}

    events = FinnhubEvents(api_key="fh-secret", transport=transport, today=date(2026, 10, 1))
    dividends = events.dividend_calendar("AAPL")
    assert dividends[0].amount == 0.25
    assert dividends[0].ex_date == date(2026, 11, 6)


def test_missing_finnhub_key_is_a_typed_error_before_any_request():
    def transport(url: str, headers: dict[str, str]):
        raise AssertionError("network")

    events = FinnhubEvents(api_key="", transport=transport, today=date(2026, 10, 1))
    with pytest.raises(MissingApiKeyError) as caught:
        events.earnings_calendar("AAPL")
    assert caught.value.env_name == "FINNHUB_API_KEY"
    assert caught.value.code == "missing_api_key"


def test_finnhub_module_does_not_request_candles():
    source = Path("src/swing/data/finnhub.py").read_text(encoding="utf-8").lower()
    assert "candle" not in source
