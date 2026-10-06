"""Bar hygiene shared by every provider and the cache.

A bar with a missing, non-finite, or non-positive price is dropped, never
coerced to 0. Sessions after the last completed NYSE session are partial and
are dropped. Only settled, vendor-final bars are written to the cache.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import replace
from datetime import date

from swing.data.models import BarSeries, DailyBar


def is_valid(bar: DailyBar) -> bool:
    prices = (bar.open, bar.high, bar.low, bar.close)
    if not all(isinstance(price, (int, float)) and math.isfinite(price) and price > 0 for price in prices):
        return False
    return math.isfinite(bar.volume) and bar.volume >= 0


def drop_invalid(bars: Iterable[DailyBar]) -> tuple[DailyBar, ...]:
    return tuple(bar for bar in bars if is_valid(bar))


def through(bars: Iterable[DailyBar], last_session: date) -> tuple[DailyBar, ...]:
    return tuple(bar for bar in bars if bar.session <= last_session)


# Price multipliers for whole-share splits. 2-for-1 cuts the price in half.
# 1-for-2 doubles it. 5-for-2 multiplies it by 0.4. A 3-for-2 only moves the
# price about 33%, which is under the 40% floor. A reverse 2-for-3 (1.5) is
# left out on purpose: a real 42% rally sits on top of 1.5 and is not a split.
_SPLIT_FACTORS: tuple[float, ...] = (
    1 / 2,
    1 / 3,
    1 / 4,
    1 / 5,
    1 / 6,
    1 / 7,
    1 / 8,
    1 / 10,
    2 / 5,
    5 / 2,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    10,
)
_SPLIT_TOLERANCE = 0.10


def split_factor(ratio: float) -> float | None:
    """The split multiplier `ratio` matches, within 10%, or None.

    `ratio` is today's close divided by yesterday's close. A match means the
    jump has the shape of a share split, not merely a large trading day.
    """
    if ratio <= 0 or not math.isfinite(ratio):
        return None
    best: float | None = None
    best_error = _SPLIT_TOLERANCE
    for factor in _SPLIT_FACTORS:
        error = abs(ratio / factor - 1.0)
        if error <= best_error:
            best = factor
            best_error = error
    return best


def first_split_gap(
    bars: Iterable[DailyBar],
    split_sessions: Iterable[date],
    *,
    threshold: float = 0.40,
) -> tuple[date, float, float, float] | None:
    """First close jump that looks like a missed split.

    Returns `(session, previous close, close, split factor)`. A listed split
    session explains the jump. A large move that is not near a split ratio is
    a real price change and is not returned.
    """
    ordered = tuple(bars)
    listed = set(split_sessions)
    for previous, bar in zip(ordered, ordered[1:], strict=False):
        if previous.close <= 0 or not math.isfinite(bar.close) or bar.session in listed:
            continue
        ratio = bar.close / previous.close
        if abs(ratio - 1.0) < threshold:
            continue
        factor = split_factor(ratio)
        if factor is None:
            continue
        return bar.session, previous.close, bar.close, factor
    return None


def unexplained_moves(
    bars: Iterable[DailyBar],
    split_sessions: Iterable[date],
    *,
    threshold: float = 0.40,
) -> tuple[str, ...]:
    """Flag a split-shaped close jump of at least `threshold` that no split lists.

    A listed split session explains the jump. A 40% trading day that is not
    near a split ratio is left alone. Dividend adjustments are not a second
    download; the split list is the only explanation.
    """
    if first_split_gap(bars, split_sessions, threshold=threshold) is None:
        return ()
    return ("unexplained_gap",)


def sanitize(
    bars: Iterable[DailyBar],
    *,
    last_session: date | None,
    split_sessions: Iterable[date] = (),
) -> tuple[tuple[DailyBar, ...], tuple[str, ...]]:
    """Drop bad prices, drop sessions after the last completed one, then flag gaps."""
    cleaned = drop_invalid(bars)
    if last_session is not None:
        cleaned = through(cleaned, last_session)
    return cleaned, unexplained_moves(cleaned, split_sessions)


def cacheable(series: BarSeries, settled: date) -> BarSeries:
    """The part of a series that may be cached: no reconstructed bar, nothing unsettled."""
    bars = series.bars[:-1] if series.reconstructed else series.bars
    return replace(series, bars=through(bars, settled), reconstructed=False)
