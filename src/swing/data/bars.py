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


def unexplained_moves(
    bars: Iterable[DailyBar],
    split_sessions: Iterable[date],
    *,
    threshold: float = 0.40,
) -> tuple[str, ...]:
    """Flag a one-day close move of at least `threshold` that no split lists.

    A listed split session explains the move. Dividend adjustments are not a
    second download; the split list is the only explanation.
    """
    ordered = tuple(bars)
    listed = set(split_sessions)
    for previous, bar in zip(ordered, ordered[1:], strict=False):
        if previous.close <= 0 or not math.isfinite(bar.close):
            continue
        change = abs(bar.close / previous.close - 1.0)
        if change >= threshold and bar.session not in listed:
            return ("unexplained_gap",)
    return ()


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
