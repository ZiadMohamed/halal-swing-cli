"""Earliest earnings date wins. A wide disagreement is a warning, not a block."""

from datetime import date

from swing.data.calendar import NyseCalendar
from swing.data.events import merge_earnings
from swing.data.models import EarningsEvent

TODAY = date(2026, 10, 1)


def _event(day: str, source: str) -> EarningsEvent:
    return EarningsEvent(ticker="AAPL", report_date=date.fromisoformat(day), hour="amc", source=source)


def test_earliest_next_report_wins_and_a_wide_gap_warns():
    merged = merge_earnings(
        (_event("2026-10-29", "finnhub"),),
        (_event("2026-10-08", "yfinance"),),
        today=TODAY,
        calendar=NyseCalendar(),
    )
    assert merged.known is True
    assert merged.next_report == date(2026, 10, 8)
    assert merged.source == "finnhub+yfinance"
    assert merged.disagree is True
    assert {event.report_date for event in merged.events} == {date(2026, 10, 8), date(2026, 10, 29)}


def test_three_sessions_apart_does_not_warn():
    merged = merge_earnings(
        (_event("2026-10-05", "finnhub"),),
        (_event("2026-10-08", "yfinance"),),
        today=TODAY,
        calendar=NyseCalendar(),
    )
    assert merged.next_report == date(2026, 10, 5)
    assert merged.disagree is False


def test_a_failed_source_does_not_clear_the_other():
    merged = merge_earnings(None, (_event("2026-10-29", "yfinance"),), today=TODAY, calendar=NyseCalendar())
    assert merged.known is True
    assert merged.source == "yfinance"
    assert merged.disagree is False


def test_empty_yahoo_without_a_next_report_is_not_a_clear_calendar():
    merged = merge_earnings(None, (), today=TODAY, calendar=NyseCalendar())
    assert merged.known is False


def test_finnhub_full_window_with_no_rows_is_a_clear_calendar():
    merged = merge_earnings((), None, today=TODAY, calendar=NyseCalendar())
    assert merged.known is True
    assert merged.source == "finnhub"
    assert merged.next_report is None


def test_override_replaces_both_calendars():
    merged = merge_earnings(
        (_event("2026-10-29", "finnhub"),),
        (_event("2026-10-08", "yfinance"),),
        today=TODAY,
        calendar=NyseCalendar(),
        override=date(2026, 11, 2),
    )
    assert merged.source == "override"
    assert merged.next_report == date(2026, 11, 2)
    assert merged.known is True
    assert merged.disagree is False
    assert merged.events[0].source == "override"


def test_last_report_is_the_latest_date_before_today():
    merged = merge_earnings(
        (_event("2026-07-30", "finnhub"), _event("2026-10-29", "finnhub")),
        (_event("2026-09-30", "yfinance"),),
        today=TODAY,
        calendar=NyseCalendar(),
    )
    assert merged.last_report == date(2026, 9, 30)
    assert merged.next_report == date(2026, 10, 29)
