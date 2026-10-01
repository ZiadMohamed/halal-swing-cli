"""NYSE next open, including holidays and early-close sessions."""

from datetime import date

import pytest

from swing.data.calendar import NyseCalendar
from swing.data.errors import DataError


def test_next_open_skips_the_weekend():
    assert NyseCalendar().next_open("2026-10-02T16:00:00-04:00") == "2026-10-05T09:30:00-04:00"


def test_next_open_skips_the_observed_independence_day_holiday():
    # 2026-07-04 is a Saturday. Friday 2026-07-03 is closed. Thursday is a full session.
    assert NyseCalendar().next_open("2026-07-02T16:00:00-04:00") == "2026-07-06T09:30:00-04:00"


def test_friday_after_thanksgiving_still_opens_even_though_it_closes_early():
    # 2025-11-27 is Thanksgiving. 2025-11-28 opens at 09:30 and closes at 13:00.
    assert NyseCalendar().next_open("2025-11-26T16:00:00-05:00") == "2025-11-28T09:30:00-05:00"


def test_before_the_open_returns_the_same_session():
    assert NyseCalendar().next_open("2026-10-05T08:00:00-04:00") == "2026-10-05T09:30:00-04:00"


def test_exactly_at_the_open_returns_the_following_session():
    assert NyseCalendar().next_open("2026-10-05T09:30:00-04:00") == "2026-10-06T09:30:00-04:00"


def test_new_year_holiday_is_skipped():
    assert NyseCalendar().next_open("2025-12-31T16:00:00-05:00") == "2026-01-02T09:30:00-05:00"


def test_session_shift_skips_the_observed_independence_day_holiday():
    calendar = NyseCalendar()
    assert calendar.is_session(date(2026, 7, 2)) is True
    assert calendar.is_session(date(2026, 7, 3)) is False
    assert calendar.shift_session(date(2026, 7, 2), 1) == date(2026, 7, 6)
    assert calendar.shift_session(date(2026, 7, 6), -2) == date(2026, 7, 1)
    assert calendar.session_on_or_before(date(2026, 7, 4)) == date(2026, 7, 2)
    assert calendar.shift_session(date(2026, 7, 6), 0) == date(2026, 7, 6)


def test_shift_session_rejects_a_non_session_at_offset_zero():
    with pytest.raises(DataError):
        NyseCalendar().shift_session(date(2026, 7, 3), 0)


def test_winter_open_uses_eastern_standard_time():
    stamp = NyseCalendar().next_open("2026-01-02T16:00:00-05:00")
    assert stamp == "2026-01-05T09:30:00-05:00"


def test_naive_timestamp_is_read_as_new_york():
    assert NyseCalendar().next_open("2026-10-02T16:00:00") == "2026-10-05T09:30:00-04:00"
