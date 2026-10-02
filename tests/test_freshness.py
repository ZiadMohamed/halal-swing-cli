"""The signal bar must be the last completed NYSE session. Offline."""

from dataclasses import replace
from datetime import date, datetime

from swing.analyze import analyze
from swing.codes import DecisionKind, ReasonCode
from swing.config import SwingConfig
from swing.data.factory import load_market_data
from swing.data.models import BarSeries
from tests.fake_yahoo import NY
from tests.synthetic import breakout_bars, equity_config, quiet_research

# Thursday 2026-10-01 01:00 New York: the last completed session is Wednesday 2026-09-30.
NOW = datetime(2026, 10, 1, 1, 0, tzinfo=NY)
SIGNAL = date(2026, 9, 30)


class _Bars:
    def __init__(self, series: BarSeries) -> None:
        self.series = series

    def fetch_daily(self, ticker: str, lookback_sessions: int) -> BarSeries:
        return self.series


class _Events:
    def earnings_calendar(self, ticker: str):
        return ()

    def dividend_calendar(self, ticker: str):
        return ()


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


def _decide(series: BarSeries, tmp_path):
    market = load_market_data(
        "AAPL", SwingConfig(), env={}, now=NOW, cache_dir=tmp_path, bars=_Bars(series), events=_Events()
    )
    return analyze("AAPL", config=equity_config(), env={}, market=market, research_result=quiet_research())


def test_a_current_bar_passes_the_freshness_gate(tmp_path):
    envelope = _decide(_series(), tmp_path)
    assert envelope.decision is DecisionKind.ENTER_LONG
    assert envelope.data.last_completed_session == "2026-09-30"


def test_stale_last_bar_is_data_stale(tmp_path):
    envelope = _decide(_series(end=date(2026, 9, 29)), tmp_path)
    assert envelope.decision is DecisionKind.NO_TRADE
    assert envelope.reasons[0].code is ReasonCode.DATA_STALE
    assert "2026-09-29" in envelope.reasons[0].message
    assert envelope.data.last_completed_session == "2026-09-30"


def test_a_reconstructed_bar_trades_with_a_warning(tmp_path):
    envelope = _decide(_series(reconstructed=True), tmp_path)
    assert envelope.decision is DecisionKind.ENTER_LONG
    assert envelope.data.reconstructed is True
    assert any(item.code is ReasonCode.WARN_BAR_RECONSTRUCTED for item in envelope.warnings)
