"""yfinance earnings, ex-dividend dates, and instrument type.

Earnings come from `Ticker.calendar` (next report) and `get_earnings_dates`
(next and recent reports with time of day). They are used when Finnhub is
missing or fails. An empty answer is not a clear calendar: the caller needs a
dated next report. Dividends are optional and never decide `events_known`.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from swing.data.errors import VendorError
from swing.data.models import DividendEvent, EarningsEvent, EarningsHour
from swing.data.yfinance_bars import YahooApi, YahooClient

_NY = ZoneInfo("America/New_York")
_RECENT_DAYS = 10
_EARNINGS_ROWS = 12
_OPEN = time(9, 30)
_CLOSE = time(16, 0)


class YahooEvents:
    def __init__(self, client: YahooApi | None = None, *, today: date | None = None) -> None:
        self._client = client or YahooClient()
        self._today = today
        self._calendars: dict[str, dict[str, Any]] = {}

    def earnings(self, ticker: str) -> tuple[EarningsEvent, ...]:
        """Recent and upcoming reports. Raises VendorError when both sources fail."""
        symbol = ticker.strip().upper()
        today = self._now_date()
        found: dict[date, EarningsHour] = {}
        failures: list[str] = []
        try:
            for day in _calendar_dates(self._calendar(symbol).get("Earnings Date")):
                found.setdefault(day, "unknown")
        except Exception as exc:  # noqa: BLE001 — vendor boundary
            failures.append(f"calendar:{type(exc).__name__}")
        try:
            frame = self._client.earnings_dates(symbol, _EARNINGS_ROWS)
            for day, hour in _earnings_rows(frame):
                if found.get(day, "unknown") == "unknown":
                    found[day] = hour
        except Exception as exc:  # noqa: BLE001 — vendor boundary
            failures.append(f"earnings_dates:{type(exc).__name__}")
        if len(failures) == 2:
            raise VendorError(",".join(failures), kind="upstream", endpoint="calendar+earnings_dates")
        floor = today - timedelta(days=_RECENT_DAYS)
        return tuple(
            EarningsEvent(ticker=symbol, report_date=day, hour=hour, source="yfinance")
            for day, hour in sorted(found.items())
            if day >= floor
        )

    def dividends(self, ticker: str) -> tuple[DividendEvent, ...]:
        """Upcoming ex-dividend date from the calendar. Amount is unknown here."""
        symbol = ticker.strip().upper()
        ex_dates = _calendar_dates(self._calendar(symbol).get("Ex-Dividend Date"))
        today = self._now_date()
        return tuple(
            DividendEvent(ticker=symbol, ex_date=day, amount=None, currency="USD")
            for day in ex_dates
            if day >= today
        )

    def instrument_type(self, ticker: str) -> str | None:
        symbol = ticker.strip().upper()
        today = self._now_date()
        _frame, meta = self._client.daily(symbol, today - timedelta(days=7), today + timedelta(days=1))
        value = meta.get("instrumentType")
        return value if isinstance(value, str) else None

    def _calendar(self, symbol: str) -> dict[str, Any]:
        if symbol not in self._calendars:
            self._calendars[symbol] = self._client.calendar(symbol) or {}
        return self._calendars[symbol]

    def _now_date(self) -> date:
        return self._today if self._today is not None else datetime.now(_NY).date()


def has_next_report(events: tuple[EarningsEvent, ...], today: date) -> bool:
    return any(event.report_date >= today for event in events)


def _calendar_dates(value: object) -> list[date]:
    items = value if isinstance(value, (list, tuple)) else [value]
    found: list[date] = []
    for item in items:
        if isinstance(item, datetime):
            found.append(item.date())
        elif isinstance(item, date):
            found.append(item)
        elif isinstance(item, pd.Timestamp) and not pd.isna(item):
            found.append(item.date())
    return found


def _earnings_rows(frame: pd.DataFrame | None) -> list[tuple[date, EarningsHour]]:
    if frame is None or frame.empty:
        return []
    index = pd.DatetimeIndex(frame.index)
    index = index.tz_localize(_NY) if index.tz is None else index.tz_convert(_NY)
    rows: list[tuple[date, EarningsHour]] = []
    for stamp in index:
        if pd.isna(stamp):
            continue
        moment = stamp.to_pydatetime()
        rows.append((moment.date(), _hour(moment.time())))
    return rows


def _hour(moment: time) -> EarningsHour:
    if moment == time(0, 0):
        return "unknown"
    if moment < _OPEN:
        return "bmo"
    if moment >= _CLOSE:
        return "amc"
    return "dmh"
