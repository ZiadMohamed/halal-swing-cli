"""Synthetic bars and envelopes for offline journal and acceptance tests."""

from __future__ import annotations

from datetime import date, timedelta

from swing.codes import DecisionKind
from swing.config import SwingConfig
from swing.data.models import BarSeries, DailyBar, DividendEvent, EarningsEvent, MarketData
from swing.disclaimer import DISCLAIMER
from swing.envelope import Envelope

SIGNAL_DAY = date(2026, 9, 30)
SUMMER_OPEN = "2026-10-05T09:30:00-04:00"
WINTER_OPEN = "2026-01-02T09:30:00-05:00"
CAIRO_SUMMER = "2026-10-05T16:30:00+03:00"
CAIRO_WINTER = "2026-01-02T16:30:00+02:00"
NY_SUMMER = "2026-10-05T09:30:00-04:00"
NY_WINTER = "2026-01-02T09:30:00-05:00"


def equity_config(equity: float | None = 100_000.0) -> SwingConfig:
    account: dict[str, object] = {"equity_usd": equity} if equity is not None else {}
    return SwingConfig.model_validate({"account": account})


def weekdays(count: int, end: date) -> list[date]:
    found: list[date] = []
    cursor = end
    while len(found) < count:
        if cursor.weekday() < 5:
            found.append(cursor)
        cursor -= timedelta(days=1)
    return list(reversed(found))


def breakout_bars(end: date = SIGNAL_DAY) -> tuple[DailyBar, ...]:
    """80 sessions that match BO_RVOL and no other setup math is asserted here."""
    closes = [100 + index * 0.05 for index in range(80)]
    prior_high = max(close + 0.4 for close in closes[-21:-1])
    last_close = prior_high + 1
    closes[-1] = last_close
    sessions = weekdays(len(closes), end)
    bars: list[DailyBar] = []
    for index, (session, close) in enumerate(zip(sessions, closes)):
        high = close + 0.4
        low = close - 0.4
        volume = 1_000_000.0
        if index == len(closes) - 1:
            close = last_close
            high = last_close + 0.2
            low = last_close - 0.2
            volume = 3_000_000.0
        bars.append(
            DailyBar(
                session=session,
                open=close,
                high=high,
                low=low,
                close=close,
                volume=volume,
                raw_close=close,
            )
        )
    return tuple(bars)


def market(
    ticker: str = "AAPL",
    *,
    next_open: str | None = SUMMER_OPEN,
    dividends: tuple[DividendEvent, ...] = (),
    earnings: tuple[EarningsEvent, ...] = (),
    events_known: bool = True,
    bars: tuple[DailyBar, ...] | None = None,
    suspect_spy: bool = False,
) -> MarketData:
    series = bars if bars is not None else breakout_bars()
    return MarketData(
        ticker=ticker,
        status="ok",
        bars_provider="yfinance",
        events_provider="finnhub",
        bars=BarSeries(
            ticker=ticker,
            provider="yfinance",
            bars=series,
            corp_action_suspect=suspect_spy,
            corp_action_reasons=("unexplained_gap",) if suspect_spy else (),
            adjustment="split_and_dividend",
        ),
        earnings=earnings,
        dividends=dividends,
        next_open=next_open,
        errors=(),
        events_known=events_known,
    )


def install_market(monkeypatch, **kwargs) -> None:
    """Replace the bar loader. SPY is suspect unless include_spy is true."""
    include_spy = kwargs.pop("include_spy", False)
    stock = market(**kwargs)

    def fake(ticker: str, config: SwingConfig, **_ignored: object) -> MarketData:
        del config
        if ticker == "SPY":
            if not include_spy:
                return market("SPY", next_open=stock.next_open, suspect_spy=True)
            return market("SPY", next_open=stock.next_open, bars=stock.bars.bars if stock.bars else None)
        return market(
            ticker,
            next_open=stock.next_open,
            dividends=stock.dividends,
            earnings=stock.earnings,
            events_known=stock.events_known,
            bars=stock.bars.bars if stock.bars else None,
        )

    monkeypatch.setattr("swing.analyze.load_market_data", fake)


def enter_envelope(
    ticker: str = "AAPL",
    *,
    entry: float = 100.0,
    stop: float = 95.0,
    target: float = 110.0,
    size_shares: int = 20,
    next_open: str = SUMMER_OPEN,
    setup: str = "BO_RVOL",
) -> Envelope:
    return Envelope(
        ticker=ticker,
        decision=DecisionKind.ENTER_LONG,
        reasons=[],
        warnings=[],
        confidence="checklist_only",
        side="long",
        plan={
            "side": "long",
            "entry": entry,
            "stop": stop,
            "target": target,
            "size_shares": size_shares,
            "next_open": next_open,
            "setup": setup,
        },
        shariah={"screened": False, "status": "user_supplied", "note": "user supplied"},
        disclaimer=DISCLAIMER,
        config_hash="ab" * 32,
        gates=[],
        stage="checklist",
    )


def no_trade_envelope(ticker: str = "AAPL") -> Envelope:
    return Envelope(
        ticker=ticker,
        decision=DecisionKind.NO_TRADE,
        reasons=[],
        warnings=[],
        confidence=None,
        side=None,
        plan=None,
        shariah={"screened": False, "status": "user_supplied", "note": "user supplied"},
        disclaimer=DISCLAIMER,
        config_hash="ab" * 32,
        gates=[],
        stage="partial",
    )
