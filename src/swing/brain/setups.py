"""Setup detectors for the locked mutex.

BO_RVOL: close above the SMA, close above the prior lookback high, and volume
at least `rvol_min` times the lookback volume SMA. That volume average excludes
today. PB_EMA: close above the trend EMA, low at or through the touch EMA, and
close back above it. RSI2_MR: close above the trend SMA and Wilder RSI strictly
below `rsi_max`. A suspect series is refused before any of this runs.
"""

from __future__ import annotations

from collections.abc import Sequence

from swing.brain.indicators import ema, rsi, sma
from swing.config import SwingConfig
from swing.data.models import BarSeries, DailyBar


class SuspectSeries(ValueError):
    """Raised when indicator code is asked to read a suspect series."""


def refuse_suspect(series: BarSeries) -> None:
    if series.corp_action_suspect:
        reasons = ", ".join(series.corp_action_reasons) or "unspecified"
        raise SuspectSeries(f"refusing indicators on a corp-action-suspect series ({reasons})")


def select_setup(order: Sequence[str], matched: set[str]) -> tuple[str | None, tuple[str, ...]]:
    winners = [name for name in order if name in matched]
    if not winners:
        return None, ()
    return winners[0], tuple(winners[1:])


def bo_rvol_signal(bars: Sequence[DailyBar], config: SwingConfig) -> bool:
    rule = config.setups.bo_rvol
    lookback = rule.breakout_lookback
    if len(bars) < max(rule.sma_period, lookback + 1):
        return False
    closes = [bar.close for bar in bars]
    average = sma(closes, rule.sma_period)
    volume_average = sma([bar.volume for bar in bars[:-1]], lookback)
    if average is None or volume_average is None or volume_average <= 0:
        return False
    prior_high = max(bar.high for bar in bars[-(lookback + 1) : -1])
    close = closes[-1]
    relative_volume = bars[-1].volume / volume_average
    return close > average and close > prior_high and relative_volume >= rule.rvol_min


def pb_ema_signal(bars: Sequence[DailyBar], config: SwingConfig) -> bool:
    rule = config.setups.pb_ema
    if len(bars) < max(rule.ema_trend, rule.ema_touch):
        return False
    closes = [bar.close for bar in bars]
    trend = ema(closes, rule.ema_trend)
    touch = ema(closes, rule.ema_touch)
    if trend is None or touch is None:
        return False
    close = closes[-1]
    return close > trend and bars[-1].low <= touch and close > touch


def rsi2_signal(bars: Sequence[DailyBar], config: SwingConfig) -> bool:
    rule = config.setups.rsi2_mr
    if len(bars) < max(rule.sma_trend, rule.rsi_period + 1):
        return False
    closes = [bar.close for bar in bars]
    trend = sma(closes, rule.sma_trend)
    reading = rsi(closes, rule.rsi_period)
    if trend is None or reading is None:
        return False
    return closes[-1] > trend and reading < rule.rsi_max
