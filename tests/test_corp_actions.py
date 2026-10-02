"""A 40% move is suspect unless that session is on the split list."""

from datetime import date

from swing.data.bars import sanitize
from swing.data.models import DailyBar


def _bar(session: str, close: float) -> DailyBar:
    return DailyBar(
        session=date.fromisoformat(session),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1_000.0,
        raw_close=close,
    )


def test_quiet_series_is_not_suspect():
    bars, reasons = sanitize(
        (
            _bar("2024-08-29", 100),
            _bar("2024-08-30", 101),
            _bar("2024-09-03", 102),
        ),
        last_session=date(2024, 9, 3),
    )
    assert reasons == ()
    assert len(bars) == 3


def test_listed_split_explains_a_large_move():
    bars, reasons = sanitize(
        (_bar("2024-08-30", 100), _bar("2024-09-03", 40)),
        last_session=date(2024, 9, 3),
        split_sessions={date(2024, 9, 3)},
    )
    assert reasons == ()
    assert bars[-1].close == 40


def test_unlisted_forty_percent_move_is_suspect():
    _bars, reasons = sanitize(
        (_bar("2024-08-30", 100), _bar("2024-09-03", 50)),
        last_session=date(2024, 9, 3),
    )
    assert reasons == ("unexplained_gap",)


def test_non_finite_prices_are_dropped_and_never_become_zero():
    bad = DailyBar(
        session=date(2024, 8, 30),
        open=float("nan"),
        high=1,
        low=1,
        close=1,
        volume=1,
        raw_close=1,
    )
    bars, reasons = sanitize((bad, _bar("2024-09-03", 10)), last_session=date(2024, 9, 3))
    assert reasons == ()
    assert [bar.session.isoformat() for bar in bars] == ["2024-09-03"]
    assert all(bar.close > 0 for bar in bars)


def test_sessions_after_the_last_completed_one_are_dropped():
    bars, _reasons = sanitize(
        (_bar("2024-08-30", 100), _bar("2024-09-03", 101)),
        last_session=date(2024, 8, 30),
    )
    assert [bar.session.isoformat() for bar in bars] == ["2024-08-30"]
