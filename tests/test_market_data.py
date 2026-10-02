"""load_market_data: earnings policy, fallbacks, ETF exemption, and freshness. Offline."""

from dataclasses import replace
from datetime import date, datetime

from swing.analyze import analyze
from swing.codes import DecisionKind, ReasonCode
from swing.config import SwingConfig
from swing.data.errors import VendorError
from swing.data.factory import load_market_data
from swing.data.finnhub import FinnhubEvents
from swing.data.models import BarSeries
from swing.data.yahoo_events import YahooEvents
from tests.fake_yahoo import NY, FakeYahoo, earnings_frame
from tests.synthetic import breakout_bars, equity_config

# Thursday 2026-10-01 01:00 New York: the last completed session is Wednesday 2026-09-30.
NOW = datetime(2026, 10, 1, 1, 0, tzinfo=NY)
SIGNAL = date(2026, 9, 30)
FINNHUB_EARNINGS = {
    "earningsCalendar": [{"symbol": "AAPL", "date": "2026-10-29", "hour": "amc", "quarter": 4, "year": 2026}]
}


class _Bars:
    def __init__(self, series: BarSeries) -> None:
        self.series = series

    def fetch_daily(self, ticker: str, lookback_sessions: int) -> BarSeries:
        return self.series


def _series(end: date = SIGNAL, **changes) -> BarSeries:
    base = BarSeries(
        ticker="AAPL",
        provider="yfinance",
        bars=breakout_bars(end),
        corp_action_suspect=False,
        corp_action_reasons=(),
        adjustment="split_and_dividend",
        instrument_type="EQUITY",
    )
    return replace(base, **changes)


def _finnhub(urls: list[str], *, earnings_error: VendorError | None = None) -> FinnhubEvents:
    def transport(url: str, headers: dict[str, str]):
        urls.append(url)
        if "/stock/dividend" in url:
            raise VendorError("You don't have access to this resource.", kind="plan_forbidden", status=403)
        if earnings_error is not None:
            raise earnings_error
        return FINNHUB_EARNINGS

    return FinnhubEvents(api_key="fh-key", transport=transport, today=NOW.date())


def _load(series: BarSeries, *, finnhub: FinnhubEvents, yahoo: FakeYahoo, tmp_path):
    return load_market_data(
        "AAPL",
        SwingConfig(),
        env={},
        now=NOW,
        cache_dir=tmp_path,
        bars=_Bars(series),
        events=finnhub,
        yahoo=YahooEvents(yahoo, today=NOW.date()),
    )


def _decide(market):
    return analyze("AAPL", config=equity_config(), env={}, market=market)


def test_finnhub_earnings_200_and_no_dividend_call_means_events_known(tmp_path):
    urls: list[str] = []
    market = _load(_series(), finnhub=_finnhub(urls), yahoo=FakeYahoo(calendar=RuntimeError("down")), tmp_path=tmp_path)
    assert market.events_known is True
    assert market.earnings_source == "finnhub"
    assert market.status == "ok"
    assert all("/stock/dividend" not in url for url in urls)
    assert not any("403" in error for error in market.errors)
    assert market.dividends == ()
    assert market.last_completed_session == SIGNAL
    assert _decide(market).decision is DecisionKind.ENTER_LONG


def test_missing_finnhub_key_falls_back_to_a_dated_yahoo_report(tmp_path):
    yahoo = FakeYahoo(
        calendar={"Earnings Date": [date(2026, 10, 29)], "Ex-Dividend Date": date(2026, 11, 9)},
        earnings=earnings_frame(["2026-10-29 16:00", "2026-07-30 16:00"]),
    )
    finnhub = FinnhubEvents(api_key="", transport=lambda *_a: None, today=NOW.date())
    market = _load(_series(), finnhub=finnhub, yahoo=yahoo, tmp_path=tmp_path)
    assert market.events_known is True
    assert market.earnings_source == "yfinance"
    assert [event.report_date for event in market.earnings] == [date(2026, 10, 29)]
    assert market.earnings[0].hour == "amc"
    assert "missing_api_key:FINNHUB_API_KEY" in market.errors
    assert market.dividends[0].ex_date == date(2026, 11, 9)
    assert market.dividends[0].amount is None
    envelope = _decide(market)
    assert envelope.decision is DecisionKind.ENTER_LONG
    assert envelope.data.earnings_source == "yfinance"


def test_finnhub_403_on_earnings_is_reported_with_endpoint_and_class_then_falls_back(tmp_path):
    forbidden = VendorError(
        "You don't have access to this resource.", kind="plan_forbidden", endpoint="/api/v1/calendar/earnings", status=403
    )
    yahoo = FakeYahoo(calendar={"Earnings Date": [date(2026, 10, 29)]})
    market = _load(_series(), finnhub=_finnhub([], earnings_error=forbidden), yahoo=yahoo, tmp_path=tmp_path)
    assert market.events_known is True
    assert market.earnings_source == "yfinance"
    finnhub_errors = [error for error in market.errors if error.startswith("vendor_error:finnhub:")]
    assert finnhub_errors == [
        "vendor_error:finnhub:/api/v1/calendar/earnings:http_403:plan_forbidden:You don't have access to this resource."
    ]


def test_empty_yahoo_answer_is_not_a_clear_calendar(tmp_path):
    finnhub = FinnhubEvents(api_key="", transport=lambda *_a: None, today=NOW.date())
    for yahoo in (
        FakeYahoo(calendar={}, earnings=None),
        FakeYahoo(calendar={}, earnings=earnings_frame(["2026-07-30 16:00"])),
        FakeYahoo(calendar=RuntimeError("down"), earnings=RuntimeError("down")),
    ):
        market = _load(_series(), finnhub=finnhub, yahoo=yahoo, tmp_path=tmp_path)
        assert market.events_known is False
        assert market.status == "partial"
        envelope = _decide(market)
        assert envelope.decision is DecisionKind.NO_TRADE
        assert envelope.reasons[0].code is ReasonCode.EARNINGS_UNKNOWN


def test_a_recent_yahoo_report_still_triggers_the_after_report_blackout(tmp_path):
    yahoo = FakeYahoo(
        calendar={"Earnings Date": [date(2027, 1, 28)]},
        earnings=earnings_frame(["2027-01-28 16:00", "2026-09-30 07:00"]),
    )
    finnhub = FinnhubEvents(api_key="", transport=lambda *_a: None, today=NOW.date())
    market = _load(_series(), finnhub=finnhub, yahoo=yahoo, tmp_path=tmp_path)
    assert market.events_known is True
    assert market.earnings[0].report_date == date(2026, 9, 30)
    assert market.earnings[0].hour == "bmo"
    assert _decide(market).reasons[0].code is ReasonCode.EARNINGS_BLACKOUT


def test_dividend_failure_never_changes_events_known(tmp_path):
    urls: list[str] = []
    yahoo = FakeYahoo(calendar=RuntimeError("quoteSummary 404"))
    market = _load(_series(), finnhub=_finnhub(urls), yahoo=yahoo, tmp_path=tmp_path)
    assert market.events_known is True
    assert market.errors == ()


def test_etf_skips_earnings_and_passes_the_gate_with_a_note(tmp_path):
    urls: list[str] = []
    yahoo = FakeYahoo(calendar={})
    market = _load(_series(instrument_type="ETF"), finnhub=_finnhub(urls), yahoo=yahoo, tmp_path=tmp_path)
    assert market.instrument_type == "ETF"
    assert market.events_known is True
    assert urls == []
    assert yahoo.count("earnings_dates") == 0
    envelope = _decide(market)
    assert envelope.decision is DecisionKind.ENTER_LONG
    assert any(item.code is ReasonCode.NOTE_ETF_NO_EARNINGS for item in envelope.warnings)
    assert next(gate.status for gate in envelope.gates if gate.name == "earnings") == "pass"


def test_unknown_instrument_type_is_looked_up_once_and_unknown_stays_strict(tmp_path):
    yahoo = FakeYahoo(meta={"instrumentType": "ETF"}, calendar={})
    market = _load(_series(instrument_type=None), finnhub=_finnhub([]), yahoo=yahoo, tmp_path=tmp_path)
    assert market.instrument_type == "ETF"
    assert yahoo.count("daily") == 1

    odd = FakeYahoo(meta={"instrumentType": "MUTUALFUND"}, calendar={})
    finnhub = FinnhubEvents(api_key="", transport=lambda *_a: None, today=NOW.date())
    market = _load(_series(instrument_type=None), finnhub=finnhub, yahoo=odd, tmp_path=tmp_path)
    assert market.instrument_type is None
    assert _decide(market).reasons[0].code is ReasonCode.EARNINGS_UNKNOWN
