"""Price indicators for the checklist.

Inputs are split-adjusted prices. `raw_close` is not an argument. Callers must
refuse a `corp_action_suspect` series before they get here.

SMA is a simple mean of the last `period` values.
EMA seeds with that SMA, then uses k = 2 / (period + 1).
RSI and ATR use Wilder smoothing.
"""

from __future__ import annotations

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


def ema_series(values: Sequence[float], period: int) -> list[float | None]:
    """EMA of each prefix. The last finite value matches `ema` on that prefix."""
    out: list[float | None] = [None] * len(values)
    if period < 1 or len(values) < period:
        return out
    k = 2 / (period + 1)
    acc = sum(values[:period]) / period
    out[period - 1] = acc
    for index, price in enumerate(values[period:], start=period):
        acc = price * k + acc * (1 - k)
        out[index] = acc
    return out


def rsi_series(closes: Sequence[float], period: int) -> list[float | None]:
    """Wilder RSI of each prefix. The last finite value matches `rsi`."""
    out: list[float | None] = [None] * len(closes)
    if period < 1 or len(closes) < period + 1:
        return out
    gains: list[float] = []
    losses: list[float] = []
    for previous, current in zip(closes, closes[1:]):
        change = current - previous
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    out[period] = 100.0 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))
    for offset, (gain, loss) in enumerate(zip(gains[period:], losses[period:]), start=period + 1):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        out[offset] = 100.0 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))
    return out


def atr_series(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int,
) -> list[float | None]:
    """Wilder ATR of each prefix. The last finite value matches `atr`."""
    out: list[float | None] = [None] * len(closes)
    if period < 1 or len(closes) < period or len(highs) != len(closes) or len(lows) != len(closes):
        return out
    ranges = _true_ranges(highs, lows, closes)
    acc = sum(ranges[:period]) / period
    out[period - 1] = acc
    for index, true_range in enumerate(ranges[period:], start=period):
        acc = (acc * (period - 1) + true_range) / period
        out[index] = acc
    return out


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
