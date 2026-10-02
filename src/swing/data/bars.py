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


def cacheable(series: BarSeries, settled: date) -> BarSeries:
    """The part of a series that may be cached: no reconstructed bar, nothing unsettled."""
    bars = series.bars[:-1] if series.reconstructed else series.bars
    return replace(series, bars=through(bars, settled), reconstructed=False)
