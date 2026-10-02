"""An offline stand-in for the yfinance network client."""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

NY = ZoneInfo("America/New_York")
NAN = math.nan


def daily_frame(rows: list[tuple[str, float, float, float, float, float]], splits: dict[str, float] | None = None):
    """Rows of (session, open, high, low, close, volume), indexed like yfinance."""
    index = pd.DatetimeIndex([pd.Timestamp(row[0]) for row in rows]).tz_localize(NY)
    split_map = splits or {}
    return pd.DataFrame(
        {
            "Open": [row[1] for row in rows],
            "High": [row[2] for row in rows],
            "Low": [row[3] for row in rows],
            "Close": [row[4] for row in rows],
            "Volume": [row[5] for row in rows],
            "Dividends": [0.0 for _ in rows],
            "Stock Splits": [split_map.get(row[0], 0.0) for row in rows],
        },
        index=index,
    )


def steady_rows(sessions: list[str], start: float = 100.0, volume: float = 1_000_000.0):
    return [
        (day, start + i, start + i + 1, start + i - 1, start + i + 0.5, volume) for i, day in enumerate(sessions)
    ]


def hourly_frame(session: str, *, count: int = 7, first: float = 200.0, open_at: time = time(9, 30)):
    day = date.fromisoformat(session)
    start = datetime.combine(day, open_at, tzinfo=NY)
    stamps = [start + timedelta(hours=i) for i in range(count)]
    opens = [first + i for i in range(count)]
    return pd.DataFrame(
        {
            "Open": opens,
            "High": [value + 2 for value in opens],
            "Low": [value - 1 for value in opens],
            "Close": [value + 0.5 for value in opens],
            "Volume": [100_000.0 for _ in opens],
        },
        index=pd.DatetimeIndex(stamps),
    )


def earnings_frame(stamps: list[str]):
    index = pd.DatetimeIndex([pd.Timestamp(stamp) for stamp in stamps])
    if index.tz is None:
        index = index.tz_localize(NY)
    return pd.DataFrame({"EPS Estimate": [1.0 for _ in stamps]}, index=index)


class FakeYahoo:
    def __init__(
        self,
        *,
        daily: pd.DataFrame | None = None,
        meta: dict | None = None,
        hourly: pd.DataFrame | Exception | None = None,
        calendar: dict | Exception | None = None,
        earnings: pd.DataFrame | Exception | None = None,
    ) -> None:
        self._daily = daily if daily is not None else pd.DataFrame()
        self._meta = meta or {}
        self._hourly = hourly
        self._calendar = calendar
        self._earnings = earnings
        self.calls: list[tuple] = []

    def daily(self, symbol: str, start: date, end: date):
        self.calls.append(("daily", symbol, start, end))
        return self._daily, dict(self._meta)

    def hourly(self, symbol: str, session: date):
        self.calls.append(("hourly", symbol, session))
        if isinstance(self._hourly, Exception):
            raise self._hourly
        if self._hourly is None:
            return pd.DataFrame()
        return self._hourly

    def calendar(self, symbol: str):
        self.calls.append(("calendar", symbol))
        if isinstance(self._calendar, Exception):
            raise self._calendar
        return self._calendar or {}

    def earnings_dates(self, symbol: str, limit: int):
        self.calls.append(("earnings_dates", symbol, limit))
        if isinstance(self._earnings, Exception):
            raise self._earnings
        return self._earnings

    def count(self, name: str) -> int:
        return sum(1 for call in self.calls if call[0] == name)
