"""Analyze attaches market data and still returns NO_TRADE."""

from datetime import date

from swing.analyze import analyze
from swing.brain.stub import ChecklistResult, StubBrain
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
from swing.research.models import ResearchResult


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


def _research() -> ResearchResult:
    return ResearchResult(status="skipped", provider="none", reason="disabled", query=None, hits=())


def test_attached_data_does_not_invent_an_entry():
    env = analyze("AAPL", env={}, market=_market(), research_result=_research())
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


def test_brain_can_accept_market_data_and_does_not_receive_research():
    seen: dict[str, object] = {}

    class _Brain:
        def evaluate(self, ticker: str, config: SwingConfig, market: MarketData | None = None) -> ChecklistResult:
            seen["ticker"] = ticker
            seen["market"] = market
            return StubBrain().evaluate(ticker, config)

    brain = _Brain()
    analyze("AAPL", env={}, market=_market(), brain=brain, research_result=_research())
    market = seen["market"]
    assert seen["ticker"] == "AAPL"
    assert isinstance(market, MarketData)
    assert market.bars is not None
    assert market.bars.corp_action_suspect is True
    assert not hasattr(market, "hits")


def test_legacy_brain_without_a_market_argument_still_runs():
    class _Brain:
        def evaluate(self, ticker: str, config: SwingConfig) -> ChecklistResult:
            return StubBrain().evaluate(ticker, config)

    env = analyze("AAPL", env={}, market=_market(), brain=_Brain(), research_result=_research())
    assert env.decision is DecisionKind.NO_TRADE
    assert env.data.bar_count == 2


def test_missing_vendor_keys_attach_typed_errors_and_stay_no_trade(tmp_path):
    cfg = SwingConfig.model_validate({"data": {"bars_provider": "massive"}})
    market = load_market_data(
        "AAPL",
        cfg,
        env={},
        cache_dir=tmp_path,
        now=__import__("datetime").datetime(2026, 10, 1, 18, 0, tzinfo=__import__("zoneinfo").ZoneInfo("America/New_York")),
    )
    env = analyze("AAPL", config=cfg, env={}, market=market, research_result=_research())
    assert env.decision is DecisionKind.NO_TRADE
    assert env.plan is None
    assert env.data.status == "error"
    assert "missing_api_key:MASSIVE_API_KEY" in env.data.errors
    assert "missing_api_key:FINNHUB_API_KEY" in env.data.errors
    assert env.data.next_open is not None
    assert env.data.next_open.endswith("-04:00")
    assert "09:30:00" in env.data.next_open
    assert env.data.events_known is False
