"""Merge Finnhub and yfinance earnings. The earliest next report wins."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from swing.data.calendar import NyseCalendar
from swing.data.models import EarningsEvent

_DISAGREE_SESSIONS = 3


@dataclass(frozen=True)
class EarningsMerge:
    events: tuple[EarningsEvent, ...]
    known: bool
    source: str | None
    disagree: bool
    next_report: date | None
    last_report: date | None


def merge_earnings(
    finnhub: tuple[EarningsEvent, ...] | None,
    yahoo: tuple[EarningsEvent, ...] | None,
    *,
    today: date,
    calendar: NyseCalendar,
    override: date | None = None,
) -> EarningsMerge:
    """Combine two calendars.

    `None` means that source failed. A tuple, including an empty one, means the
    source answered. An empty answer is a clear calendar only when Finnhub
    returned that full window. Yahoo still needs a dated next report.
    """
    if override is not None:
        event = EarningsEvent(ticker=_ticker(finnhub, yahoo), report_date=override, hour="unknown", source="override")
        return EarningsMerge((event,), True, "override", False, override, _last((), today))

    pool: list[EarningsEvent] = []
    if finnhub:
        pool.extend(finnhub)
    if yahoo:
        pool.extend(yahoo)
    pool.sort(key=lambda item: (item.report_date, item.source or ""))
    next_finnhub = _next(finnhub, today)
    next_yahoo = _next(yahoo, today)
    disagree = False
    source: str | None = None
    chosen: date | None = None
    if next_finnhub is not None and next_yahoo is not None:
        chosen = min(next_finnhub, next_yahoo)
        source = "finnhub+yfinance"
        disagree = calendar.sessions_between(next_finnhub, next_yahoo) > _DISAGREE_SESSIONS
    elif next_finnhub is not None:
        chosen = next_finnhub
        source = "finnhub"
    elif next_yahoo is not None:
        chosen = next_yahoo
        source = "yfinance"
    elif finnhub is not None:
        # Full-window response with no upcoming report.
        source = "finnhub"
        return EarningsMerge(tuple(pool), True, source, False, None, _last(pool, today))
    else:
        return EarningsMerge(tuple(pool), False, None, False, None, _last(pool, today))
    return EarningsMerge(tuple(pool), True, source, disagree, chosen, _last(pool, today))


def _next(events: tuple[EarningsEvent, ...] | None, today: date) -> date | None:
    if not events:
        return None
    upcoming = [event.report_date for event in events if event.report_date >= today]
    return min(upcoming) if upcoming else None


def _last(events: tuple[EarningsEvent, ...] | list[EarningsEvent], today: date) -> date | None:
    prior = [event.report_date for event in events if event.report_date < today]
    return max(prior) if prior else None


def _ticker(finnhub: tuple[EarningsEvent, ...] | None, yahoo: tuple[EarningsEvent, ...] | None) -> str:
    for group in (finnhub, yahoo):
        if group:
            return group[0].ticker
    return ""
