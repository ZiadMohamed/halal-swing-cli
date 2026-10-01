"""Price indicators for the checklist.

Inputs are split-adjusted prices. `raw_close` is not an argument. Callers must
refuse a `corp_action_suspect` series before they get here.

SMA is a simple mean of the last `period` values.
EMA seeds with that SMA, then uses k = 2 / (period + 1).
RSI and ATR use Wilder smoothing. R² is the square of the Pearson correlation.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def sma(values: Sequence[float], period: int) -> float | None:
    if period < 1 or len(values) < period:
        return None
    window = values[-period:]
    return sum(window) / period


def ema(values: Sequence[float], period: int) -> float | None:
    if period < 1 or len(values) < period:
        return None
    k = 2 / (period + 1)
    acc = sum(values[:period]) / period
    for price in values[period:]:
        acc = price * k + acc * (1 - k)
    return acc


def rsi(closes: Sequence[float], period: int) -> float | None:
    if period < 1 or len(closes) < period + 1:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for previous, current in zip(closes, closes[1:]):
        change = current - previous
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int,
) -> float | None:
    if period < 1 or len(closes) < period or len(highs) != len(closes) or len(lows) != len(closes):
        return None
    ranges = _true_ranges(highs, lows, closes)
    acc = sum(ranges[:period]) / period
    for true_range in ranges[period:]:
        acc = (acc * (period - 1) + true_range) / period
    return acc


def r_squared(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    count = len(left)
    mean_left = sum(left) / count
    mean_right = sum(right) / count
    var_left = sum((value - mean_left) ** 2 for value in left)
    var_right = sum((value - mean_right) ** 2 for value in right)
    if var_left == 0 or var_right == 0:
        return None
    covariance = sum((a - mean_left) * (b - mean_right) for a, b in zip(left, right))
    correlation = covariance / math.sqrt(var_left * var_right)
    return correlation * correlation


def _true_ranges(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
) -> list[float]:
    ranges = [highs[0] - lows[0]]
    for index in range(1, len(closes)):
        ranges.append(
            max(
                highs[index] - lows[index],
                abs(highs[index] - closes[index - 1]),
                abs(lows[index] - closes[index - 1]),
            )
        )
    return ranges
