"""yfinance daily bars. Prototype vendor. Not used for events."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from swing.data.cache import read_fresh_bars, write_bars
from swing.data.calendar import NyseCalendar
from swing.data.corp_actions import assess_corp_actions
from swing.data.errors import VendorError
from swing.data.models import BarSeries, CorporateAction, DailyBar

_NY = ZoneInfo("America/New_York")
_Download = Callable[[str, date, date], tuple[pd.DataFrame, pd.DataFrame]]


class YFinanceBarProvider:
    """Split-and-dividend adjusted OHLC from yfinance, cached as Parquet."""

    def __init__(
        self,
        *,
        cache_dir,
        download: _Download | None = None,
        now: Callable[[], datetime] | None = None,
        calendar: NyseCalendar | None = None,
    ) -> None:
        self._cache_dir = cache_dir
        self._download = download or download_yfinance
        self._now = now or (lambda: datetime.now(_NY))
        self._calendar = calendar or NyseCalendar()

    def fetch_daily(self, ticker: str, lookback_sessions: int) -> BarSeries:
        symbol = ticker.strip().upper()
        now = self._now()
        cached = read_fresh_bars(self._cache_dir, symbol, lookback_sessions, now, self._calendar)
        if cached is not None:
            return cached
        start = now.date() - timedelta(days=lookback_sessions * 2 + 30)
        end = now.date() + timedelta(days=1)
        try:
            adjusted, raw = self._download(symbol, start, end)
        except VendorError:
            raise
        except Exception as exc:  # noqa: BLE001 — vendor boundary
            raise VendorError(f"{type(exc).__name__}") from exc
        series = bars_from_yfinance_frames(symbol, adjusted, raw)
        if not series.bars:
            raise VendorError("empty_bars")
        write_bars(self._cache_dir, series)
        return series.sliced(lookback_sessions)


def download_yfinance(ticker: str, start: date, end: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Network call. Tests inject a download function and never reach this."""
    import yfinance as yf

    handle = yf.Ticker(ticker)
    adjusted = handle.history(
        start=start.isoformat(),
        end=end.isoformat(),
        interval="1d",
        auto_adjust=True,
        actions=True,
        repair=False,
    )
    raw = handle.history(
        start=start.isoformat(),
        end=end.isoformat(),
        interval="1d",
        auto_adjust=False,
        actions=False,
        repair=False,
    )
    return adjusted, raw


def bars_from_yfinance_frames(ticker: str, adjusted: pd.DataFrame, raw: pd.DataFrame) -> BarSeries:
    adjusted_rows = _rows(adjusted)
    raw_rows = {row[0]: row for row in _rows(raw)}
    bars: list[DailyBar] = []
    actions: list[CorporateAction] = []
    for session, open_, high, low, close, volume, dividend, split in adjusted_rows:
        raw = raw_rows.get(session)
        if raw is None:
            continue
        bars.append(
            DailyBar(
                session=session,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume,
                raw_close=raw[4],
            )
        )
        if split and split > 0:
            actions.append(CorporateAction(session=session, kind="split", split_to=split, split_from=1.0))
        if dividend and dividend > 0:
            actions.append(CorporateAction(session=session, kind="dividend", amount=dividend))
    ordered = tuple(bars)
    assessment = assess_corp_actions(ordered, actions, adjustment="split_and_dividend")
    return BarSeries(
        ticker=ticker,
        provider="yfinance",
        bars=ordered,
        corp_action_suspect=assessment.suspect,
        corp_action_reasons=assessment.reasons,
        adjustment="split_and_dividend",
    )


def _rows(frame: pd.DataFrame) -> list[tuple]:
    if frame is None or frame.empty:
        return []
    data = frame.copy()
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    index = data.index
    if getattr(index, "tz", None) is None:
        index = index.tz_localize(_NY)
    else:
        index = index.tz_convert(_NY)
    rows = []
    for position, label in enumerate(index):
        record = data.iloc[position]
        rows.append(
            (
                label.date(),
                _float(record, "Open"),
                _float(record, "High"),
                _float(record, "Low"),
                _float(record, "Close"),
                _float(record, "Volume"),
                _float(record, "Dividends"),
                _float(record, "Stock Splits"),
            )
        )
    return rows


def _float(record, name: str) -> float:
    if name not in record.index:
        return 0.0
    value = record[name]
    if pd.isna(value):
        return 0.0
    return float(value)
