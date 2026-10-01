"""NYSE session clock. Holidays and early closes come from the exchange calendar."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from swing.data.errors import DataError

_NY = ZoneInfo("America/New_York")


class NyseCalendar:
    """Next regular-session open, as an ISO timestamp in America/New_York.

    Early-close days still open at 09:30. They are sessions, not holidays.
    `after_iso` is exclusive: a timestamp exactly at the open returns the
    following session. A naive timestamp is read as America/New_York.
    """

    def __init__(self) -> None:
        self._calendar = None

    def next_open(self, after_iso: str) -> str:
        moment = _parse(after_iso)
        calendar = self._xnys()
        start = moment.date()
        sessions = calendar.sessions_in_range(
            _timestamp(start),
            _timestamp(start + timedelta(days=14)),
        )
        for session in sessions:
            opened = calendar.session_open(session).tz_convert(_NY).to_pydatetime()
            if opened > moment:
                return opened.isoformat(timespec="seconds")
        raise DataError("no upcoming NYSE open", code="calendar")

    def last_completed_session(self, now: datetime) -> date:
        moment = _as_ny(now)
        calendar = self._xnys()
        start = moment.date() - timedelta(days=14)
        sessions = calendar.sessions_in_range(_timestamp(start), _timestamp(moment.date()))
        completed: date | None = None
        for session in sessions:
            closed = calendar.session_close(session).tz_convert(_NY).to_pydatetime()
            if closed <= moment:
                completed = session.date()
        if completed is None:
            raise DataError("no completed NYSE session", code="calendar")
        return completed

    def _xnys(self):
        if self._calendar is None:
            import exchange_calendars as xcals

            self._calendar = xcals.get_calendar("XNYS")
        return self._calendar


def _parse(after_iso: str) -> datetime:
    text = after_iso.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return _as_ny(datetime.fromisoformat(text))


def _as_ny(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=_NY)
    return moment.astimezone(_NY)


def _timestamp(day: date):
    import pandas as pd

    return pd.Timestamp(day)
