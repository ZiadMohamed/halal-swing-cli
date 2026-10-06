"""Parquet cache under bars_cache_dir(). OHLC in the file is split-adjusted.

Providers write only settled, vendor-final bars (see `swing.data.bars.cacheable`).
Reading drops any invalid row, so a cache written before the NaN fix cannot
pass a zero-price bar to the checklist.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from swing.data.bars import drop_invalid, unexplained_moves
from swing.data.calendar import NyseCalendar
from swing.data.models import BarSeries, DailyBar


def write_bars(cache_dir: Path, series: BarSeries) -> Path | None:
    bars = drop_invalid(series.bars)
    if not bars:
        return None
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{_safe_ticker(series.ticker)}.parquet"
    table = pa.table(
        {
            "session": pa.array([bar.session for bar in bars], type=pa.date32()),
            "open": pa.array([bar.open for bar in bars], type=pa.float64()),
            "high": pa.array([bar.high for bar in bars], type=pa.float64()),
            "low": pa.array([bar.low for bar in bars], type=pa.float64()),
            "close": pa.array([bar.close for bar in bars], type=pa.float64()),
            "volume": pa.array([bar.volume for bar in bars], type=pa.float64()),
            "raw_close": pa.array([bar.raw_close for bar in bars], type=pa.float64()),
        }
    )
    metadata = {
        b"ticker": series.ticker.encode(),
        b"provider": series.provider.encode(),
        b"adjustment": series.adjustment.encode(),
        b"corp_action_suspect": b"true" if series.corp_action_suspect else b"false",
        b"corp_action_reasons": ",".join(series.corp_action_reasons).encode(),
        b"instrument_type": (series.instrument_type or "").encode(),
    }
    pq.write_table(table.replace_schema_metadata(metadata), path)
    return path


def read_bars(cache_dir: Path, ticker: str) -> BarSeries | None:
    path = cache_dir / f"{_safe_ticker(ticker)}.parquet"
    if not path.is_file():
        return None
    table = pq.read_table(path)
    meta = table.schema.metadata or {}
    sessions = table.column("session").to_pylist()
    opens = table.column("open").to_pylist()
    highs = table.column("high").to_pylist()
    lows = table.column("low").to_pylist()
    closes = table.column("close").to_pylist()
    volumes = table.column("volume").to_pylist()
    raws = table.column("raw_close").to_pylist()
    bars = drop_invalid(
        DailyBar(
            session=_as_date(session),
            open=_num(open_),
            high=_num(high),
            low=_num(low),
            close=_num(close),
            volume=_num(volume),
            raw_close=_num(raw),
        )
        for session, open_, high, low, close, volume, raw in zip(
            sessions, opens, highs, lows, closes, volumes, raws, strict=True
        )
    )
    stored_reasons = tuple(part for part in meta.get(b"corp_action_reasons", b"").decode().split(",") if part)
    # A fresh rule can clear a stale unexplained_gap. The split list is not in
    # the file; adjusted closes only still jump when the gap was a real one.
    if "unexplained_gap" in stored_reasons:
        fresh_gap = unexplained_moves(bars, ())
        reasons = tuple(part for part in stored_reasons if part != "unexplained_gap") + fresh_gap
        suspect = bool(reasons)
    else:
        reasons = stored_reasons
        suspect = meta.get(b"corp_action_suspect", b"false") == b"true"
    adjustment = meta.get(b"adjustment", b"split").decode()
    if adjustment not in {"split", "split_and_dividend"}:
        adjustment = "split"
    instrument = meta.get(b"instrument_type", b"").decode() or None
    return BarSeries(
        ticker=meta.get(b"ticker", ticker.encode()).decode(),
        provider=meta.get(b"provider", b"cache").decode(),
        bars=bars,
        corp_action_suspect=suspect,
        corp_action_reasons=reasons,
        adjustment=adjustment,  # type: ignore[arg-type]
        instrument_type=instrument,
    )


def read_fresh_bars(
    cache_dir: Path,
    ticker: str,
    lookback: int,
    now: datetime,
    calendar: NyseCalendar,
) -> BarSeries | None:
    """Return cached bars when they already cover the last completed session."""
    cached = read_bars(cache_dir, ticker)
    if cached is None or len(cached.bars) < lookback:
        return None
    if cached.bars[-1].session != calendar.last_completed_session(now):
        return None
    return cached.sliced(lookback)


def _safe_ticker(ticker: str) -> str:
    symbol = ticker.strip().upper()
    if not symbol or any(char in symbol for char in "/\\"):
        raise ValueError(f"Not a ticker: {ticker!r}")
    return symbol


def _as_date(value: date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value


def _num(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return float("nan")
