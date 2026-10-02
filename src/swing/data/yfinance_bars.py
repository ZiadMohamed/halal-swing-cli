"""yfinance daily bars. Fallback vendor; also the source of instrument type.

One auto-adjusted `history()` call per ticker. Rows with a missing or
non-positive price are dropped (Yahoo often serves the latest session with
NaN open/high/low/close until the next open). Sessions after the last
completed NYSE session are partial and are dropped. When the last completed
session is missing after that, it is rebuilt from 1-hour regular-session bars,
keeping the daily row's volume when Yahoo gave one, and flagged
`reconstructed`. A reconstructed or unsettled bar is never cached.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import pandas as pd

from swing.data.bars import cacheable, drop_invalid, is_valid, through
from swing.data.cache import read_fresh_bars, write_bars
from swing.data.calendar import NyseCalendar
from swing.data.bars import sanitize
from swing.data.errors import VendorError
from swing.data.models import BarSeries, DailyBar

_NY = ZoneInfo("America/New_York")
_HOUR = timedelta(hours=1)


class YahooApi(Protocol):
    def daily(self, symbol: str, start: date, end: date) -> tuple[pd.DataFrame, dict[str, Any]]: ...

    def hourly(self, symbol: str, session: date) -> pd.DataFrame: ...

    def calendar(self, symbol: str) -> dict[str, Any]: ...

    def earnings_dates(self, symbol: str, limit: int) -> pd.DataFrame | None: ...


class YahooClient:
    """The only code that calls the yfinance network API. Tests inject a fake."""

    def __init__(self) -> None:
        self._handles: dict[str, Any] = {}

    def daily(self, symbol: str, start: date, end: date) -> tuple[pd.DataFrame, dict[str, Any]]:
        handle = self._handle(symbol)
        frame = handle.history(
            start=start.isoformat(),
            end=end.isoformat(),
            interval="1d",
            auto_adjust=True,
            actions=True,
            repair=False,
        )
        meta: dict[str, Any] = {}
        try:
            raw = handle.get_history_metadata()
            for key in ("instrumentType", "currency"):
                value = raw.get(key)
                if isinstance(value, str):
                    meta[key] = value
        except Exception:  # noqa: BLE001 — metadata is optional
            pass
        return frame, meta

    def hourly(self, symbol: str, session: date) -> pd.DataFrame:
        return self._handle(symbol).history(
            start=session.isoformat(),
            end=(session + timedelta(days=1)).isoformat(),
            interval="1h",
            auto_adjust=True,
            actions=False,
            prepost=False,
            repair=False,
        )

    def calendar(self, symbol: str) -> dict[str, Any]:
        result = self._handle(symbol).calendar
        return result if isinstance(result, dict) else {}

    def earnings_dates(self, symbol: str, limit: int) -> pd.DataFrame | None:
        return self._handle(symbol).get_earnings_dates(limit=limit)

    def _handle(self, symbol: str) -> Any:
        if symbol not in self._handles:
            import yfinance as yf

            self._handles[symbol] = yf.Ticker(symbol)
        return self._handles[symbol]


@dataclass(frozen=True)
class _Row:
    session: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    split: float


class YFinanceBarProvider:
    """Split-and-dividend adjusted OHLC from yfinance, cached as Parquet."""

    def __init__(
        self,
        *,
        cache_dir,
        client: YahooApi | None = None,
        now: Callable[[], datetime] | None = None,
        calendar: NyseCalendar | None = None,
    ) -> None:
        self._cache_dir = cache_dir
        self._client = client or YahooClient()
        self._now = now or (lambda: datetime.now(_NY))
        self._calendar = calendar or NyseCalendar()

    def fetch_daily(self, ticker: str, lookback_sessions: int) -> BarSeries:
        symbol = ticker.strip().upper()
        now = self._now()
        cached = read_fresh_bars(self._cache_dir, symbol, lookback_sessions, now, self._calendar)
        if cached is not None:
            return cached
        expected = self._calendar.last_completed_session(now)
        start = now.date() - timedelta(days=lookback_sessions * 2 + 30)
        end = now.date() + timedelta(days=1)
        try:
            frame, meta = self._client.daily(symbol, start, end)
        except VendorError:
            raise
        except Exception as exc:  # noqa: BLE001 — vendor boundary
            raise VendorError(type(exc).__name__, kind="upstream", endpoint="history") from None
        rows = _rows(frame)
        tail_volume = next((row.volume for row in rows if row.session == expected), None)
        bars = list(through(drop_invalid(_bar(row) for row in rows), expected))
        if not bars:
            raise VendorError("empty_bars", kind="upstream", endpoint="history")
        reconstructed = False
        if bars[-1].session != expected:
            rebuilt = self._rebuild(symbol, expected, tail_volume)
            if rebuilt is not None:
                bars.append(rebuilt)
                reconstructed = True
        kept = {bar.session for bar in bars}
        split_sessions = {
            row.session
            for row in rows
            if row.session in kept and math.isfinite(row.split) and row.split > 0
        }
        ordered, reasons = sanitize(tuple(bars), last_session=expected, split_sessions=split_sessions)
        series = BarSeries(
            ticker=symbol,
            provider="yfinance",
            bars=ordered,
            corp_action_suspect=bool(reasons),
            corp_action_reasons=reasons,
            adjustment="split_and_dividend",
            reconstructed=reconstructed,
            instrument_type=meta.get("instrumentType"),
        )
        write_bars(self._cache_dir, cacheable(series, self._calendar.last_settled_session(now)))
        return series.sliced(lookback_sessions)

    def _rebuild(self, symbol: str, session: date, daily_volume: float | None) -> DailyBar | None:
        """Rebuild one regular session from 1-hour bars, or None if they do not cover it."""
        try:
            frame = self._client.hourly(symbol, session)
        except Exception:  # noqa: BLE001 — a failed rebuild leaves the series stale
            return None
        opened = self._calendar.session_open(session)
        closed = self._calendar.session_close(session)
        hours = [row for row in _hourly(frame) if opened <= row[0] < closed]
        needed = math.ceil((closed - opened) / _HOUR)
        if len(hours) < needed or hours[0][0] != opened or hours[-1][0] < closed - _HOUR:
            return None
        prices = [value for row in hours for value in row[1:5]]
        if not all(math.isfinite(value) and value > 0 for value in prices):
            return None
        if daily_volume is not None and math.isfinite(daily_volume) and daily_volume > 0:
            volume = daily_volume
        else:
            volume = sum(row[5] for row in hours if math.isfinite(row[5]))
        close = hours[-1][4]
        bar = DailyBar(
            session=session,
            open=hours[0][1],
            high=max(row[2] for row in hours),
            low=min(row[3] for row in hours),
            close=close,
            volume=volume,
            raw_close=close,
        )
        return bar if is_valid(bar) else None


def _bar(row: _Row) -> DailyBar:
    # A single auto-adjusted download has no separate raw close.
    return DailyBar(
        session=row.session,
        open=row.open,
        high=row.high,
        low=row.low,
        close=row.close,
        volume=row.volume,
        raw_close=row.close,
    )


def _ny_index(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    data = frame.copy()
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    index = pd.DatetimeIndex(data.index)
    index = index.tz_localize(_NY) if index.tz is None else index.tz_convert(_NY)
    return data, index


def _rows(frame: pd.DataFrame | None) -> list[_Row]:
    if frame is None or frame.empty:
        return []
    data, index = _ny_index(frame)
    rows: list[_Row] = []
    for position, label in enumerate(index):
        record = data.iloc[position]
        rows.append(
            _Row(
                session=label.date(),
                open=_float(record, "Open"),
                high=_float(record, "High"),
                low=_float(record, "Low"),
                close=_float(record, "Close"),
                volume=_float(record, "Volume"),
                split=_float(record, "Stock Splits"),
            )
        )
    return rows


def _hourly(frame: pd.DataFrame | None) -> list[tuple[datetime, float, float, float, float, float]]:
    if frame is None or frame.empty:
        return []
    data, index = _ny_index(frame)
    found = []
    for position, label in enumerate(index):
        record = data.iloc[position]
        found.append(
            (
                label.to_pydatetime(),
                _float(record, "Open"),
                _float(record, "High"),
                _float(record, "Low"),
                _float(record, "Close"),
                _float(record, "Volume"),
            )
        )
    found.sort(key=lambda row: row[0])
    return found


def _float(record, name: str) -> float:
    """Missing or NaN stays NaN so the row is dropped, never read as 0."""
    if name not in record.index:
        return math.nan
    value = record[name]
    if value is None or pd.isna(value):
        return math.nan
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan
