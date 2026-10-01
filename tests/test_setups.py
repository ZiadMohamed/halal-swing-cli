"""Setup geometry and the BO > PB > RSI2 mutex. No network."""

from datetime import date, timedelta

import pytest

from swing.brain.indicators import rsi
from swing.brain.setups import (
    SuspectSeries,
    bo_rvol_signal,
    pb_ema_signal,
    refuse_suspect,
    rsi2_signal,
    select_setup,
)
from swing.config import SwingConfig
from swing.data.models import BarSeries, DailyBar


def _days(count: int, end: date) -> list[date]:
    found: list[date] = []
    cursor = end
    while len(found) < count:
        if cursor.weekday() < 5:
            found.append(cursor)
        cursor -= timedelta(days=1)
    return list(reversed(found))


def _bars(
    closes: list[float],
    *,
    end: date,
    volume: float = 1_000_000,
    high_pad: float = 1,
    low_pad: float = 1,
    last_volume: float | None = None,
    last_high: float | None = None,
    last_low: float | None = None,
) -> tuple[DailyBar, ...]:
    days = _days(len(closes), end)
    bars: list[DailyBar] = []
    for index, (session, close) in enumerate(zip(days, closes)):
        is_last = index == len(closes) - 1
        bars.append(
            DailyBar(
                session=session,
                open=close,
                high=last_high if is_last and last_high is not None else close + high_pad,
                low=last_low if is_last and last_low is not None else close - low_pad,
                close=close,
                volume=last_volume if is_last and last_volume is not None else volume,
                raw_close=0.0,
            )
        )
    return tuple(bars)


def test_mutex_order_is_breakout_then_pullback_then_rsi2():
    winner, suppressed = select_setup(
        ("BO_RVOL", "PB_EMA", "RSI2_MR"),
        {"RSI2_MR", "BO_RVOL", "PB_EMA"},
    )
    assert winner == "BO_RVOL"
    assert suppressed == ("PB_EMA", "RSI2_MR")
    assert select_setup(("BO_RVOL", "PB_EMA", "RSI2_MR"), set()) == (None, ())
    winner, suppressed = select_setup(("BO_RVOL", "PB_EMA", "RSI2_MR"), {"RSI2_MR"})
    assert winner == "RSI2_MR"
    assert suppressed == ()


def test_breakout_requires_a_new_high_sma50_and_rvol_at_least_1_5():
    end = date(2026, 9, 30)
    quiet = [100.0] * 59 + [110.0]
    config = SwingConfig()
    assert bo_rvol_signal(_bars(quiet, end=end, volume=100, last_volume=150), config) is True
    assert bo_rvol_signal(_bars(quiet, end=end, volume=100, last_volume=149), config) is False
    no_break = [100.0] * 60
    assert bo_rvol_signal(_bars(no_break, end=end, last_volume=500), config) is False


def test_pullback_needs_a_touch_of_ema20_and_a_close_back_above_it_in_an_uptrend():
    end = date(2026, 9, 30)
    closes = [50.0 + index for index in range(60)]
    config = SwingConfig()
    touched = _bars(closes, end=end, last_low=0.5)
    assert pb_ema_signal(touched, config) is True
    no_touch = _bars(closes, end=end)
    assert pb_ema_signal(no_touch, config) is False


def test_rsi2_is_strictly_below_10_and_above_sma200():
    end = date(2026, 9, 30)
    up = [100.0 + index * 0.2 for index in range(210)]
    config = SwingConfig()
    assert rsi(up, 2) == pytest.approx(100)
    assert rsi2_signal(_bars(up, end=end), config) is False
    dipped = up[:-6] + [up[-7] - 0.4 * step for step in range(1, 7)]
    # The last six closes step down, so RSI(2) collapses, and the level stays above the SMA.
    assert rsi(dipped, 2) < 10
    assert dipped[-1] > sum(dipped[-200:]) / 200
    assert rsi2_signal(_bars(dipped, end=end), config) is True


def test_suspect_series_is_refused_before_indicators():
    series = BarSeries(
        ticker="AAPL",
        provider="yfinance",
        bars=_bars([100.0, 101.0], end=date(2026, 9, 30)),
        corp_action_suspect=True,
        corp_action_reasons=("missing_split",),
        adjustment="split_and_dividend",
    )
    with pytest.raises(SuspectSeries):
        refuse_suspect(series)
    clean = BarSeries(
        ticker="AAPL",
        provider="yfinance",
        bars=series.bars,
        corp_action_suspect=False,
        corp_action_reasons=(),
        adjustment="split_and_dividend",
    )
    refuse_suspect(clean)
