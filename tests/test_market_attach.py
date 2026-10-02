"""Analyze attaches market data and still returns NO_TRADE."""

from datetime import date

from swing.analyze import analyze
from swing.brain.result import ChecklistResult
from swing.codes import DecisionKind, ReasonCode
from swing.config import SwingConfig
from swing.data.factory import load_market_data
from swing.data.models import (
    BarSeries,
    DailyBar,
    DividendEvent,
    EarningsEvent,
    MarketData,
)
from swing.data.yahoo_events import YahooEvents
from tests.fake_yahoo import FakeYahoo


def _market() -> MarketData:
    bars = BarSeries(
        ticker="AAPL",
        provider="yfinance",
        bars=(
            DailyBar(
                session=date(2026, 9, 29),
                open=100,
                high=101,
                low=99,
                close=100,
                volume=10,
                raw_close=100,
            ),
            DailyBar(
                session=date(2026, 9, 30),
                open=100,
                high=102,
                low=99,
                close=101,
                volume=11,
                raw_close=101,
            ),
        ),
        corp_action_suspect=True,
        corp_action_reasons=("missing_split",),
        adjustment="split_and_dividend",
    )
    return MarketData(
        ticker="AAPL",
        status="ok",
        bars_provider="yfinance",
        events_provider="finnhub",
        bars=bars,
        earnings=(
            EarningsEvent(
                ticker="AAPL",
                report_date=date(2026, 10, 29),
                hour="amc",
                quarter=4,
                year=2026,
            ),
        ),
        dividends=(
            DividendEvent(
                ticker="AAPL",
                ex_date=date(2026, 11, 6),
                amount=0.26,
                currency="USD",
                pay_date=date(2026, 11, 13),
            ),
        ),
        next_open="2026-10-02T09:30:00-04:00",
        errors=(),
    )


def test_attached_data_does_not_invent_an_entry():
    env = analyze("AAPL", env={}, market=_market())
    assert env.decision is DecisionKind.NO_TRADE
    assert env.confidence is None
    assert env.side is None
    assert env.plan is None
    assert env.stage == "partial"
    assert env.reasons[0].code is ReasonCode.CORP_ACTION_SUSPECT
    assert env.data.status == "ok"
    assert env.data.bars_provider == "yfinance"
    assert env.data.bar_count == 2
    assert env.data.first_session == "2026-09-29"
    assert env.data.last_session == "2026-09-30"
    assert env.data.corp_action_suspect is True
    assert env.data.corp_action_reasons == ["missing_split"]
    assert env.data.earnings[0].report_date == "2026-10-29"
    assert env.data.earnings[0].hour == "amc"
    assert env.data.dividends[0].ex_date == "2026-11-06"
    assert env.data.dividends[0].amount == 0.26
    assert env.data.next_open == "2026-10-02T09:30:00-04:00"
    assert env.data.errors == []
    assert env.data.events_known is True


def test_brain_receives_market_positions_and_sector_and_not_research():
    seen: dict[str, object] = {}

    class _Brain:
        def evaluate(self, ticker: str, config: SwingConfig, *, market=None, positions=(), sector=None) -> ChecklistResult:
            seen["ticker"] = ticker
            seen["market"] = market
            seen["positions"] = positions
            seen["sector"] = sector
            seen["kwargs"] = set(locals())
            return ChecklistResult(
                decision=DecisionKind.NO_TRADE,
                reasons=(),
                warnings=(),
                confidence=None,
                side=None,
                plan=None,
                gates=(),
            )

    analyze("AAPL", env={}, market=_market(), brain=_Brain(), positions=(), sector="tech")
    market = seen["market"]
    assert seen["ticker"] == "AAPL"
    assert isinstance(market, MarketData)
    assert market.bars is not None
    assert market.bars.corp_action_suspect is True
    assert seen["sector"] == "tech"
    assert "research" not in seen


def test_missing_vendor_keys_attach_typed_errors_and_stay_no_trade(tmp_path):
    cfg = SwingConfig.model_validate({"data": {"bars_provider": "massive"}})
    market = load_market_data(
        "AAPL",
        cfg,
        env={},
        cache_dir=tmp_path,
        now=__import__("datetime").datetime(2026, 10, 1, 18, 0, tzinfo=__import__("zoneinfo").ZoneInfo("America/New_York")),
        yahoo=YahooEvents(FakeYahoo(calendar=RuntimeError("offline"), earnings=RuntimeError("offline"))),
    )
    env = analyze("AAPL", config=cfg, env={}, market=market)
    assert env.decision is DecisionKind.NO_TRADE
    assert env.plan is None
    assert env.data.status == "error"
    assert "missing_api_key:MASSIVE_API_KEY" in env.data.errors
    assert "missing_api_key:FINNHUB_API_KEY" in env.data.errors
    assert any(error.startswith("vendor_error:yfinance:calendar+earnings_dates:upstream") for error in env.data.errors)
    assert env.data.next_open is not None
    assert env.data.next_open.endswith("-04:00")
    assert "09:30:00" in env.data.next_open
    assert env.data.events_known is False
