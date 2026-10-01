"""Parquet cache under bars_cache_dir(). OHLC in the file is split-adjusted."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from swing.data.calendar import NyseCalendar
from swing.data.models import Adjustment, BarSeries, DailyBar


def write_bars(cache_dir: Path, series: BarSeries) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{_safe_ticker(series.ticker)}.parquet"
    table = pa.table(
        {
            "session": pa.array([bar.session for bar in series.bars], type=pa.date32()),
            "open": pa.array([bar.open for bar in series.bars], type=pa.float64()),
            "high": pa.array([bar.high for bar in series.bars], type=pa.float64()),
            "low": pa.array([bar.low for bar in series.bars], type=pa.float64()),
            "close": pa.array([bar.close for bar in series.bars], type=pa.float64()),
            "volume": pa.array([bar.volume for bar in series.bars], type=pa.float64()),
            "raw_close": pa.array([bar.raw_close for bar in series.bars], type=pa.float64()),
        }
    )
    metadata = {
        b"ticker": series.ticker.encode(),
        b"provider": series.provider.encode(),
        b"adjustment": series.adjustment.encode(),
        b"corp_action_suspect": b"true" if series.corp_action_suspect else b"false",
        b"corp_action_reasons": ",".join(series.corp_action_reasons).encode(),
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
    bars = tuple(
        DailyBar(
            session=_as_date(session),
            open=float(open_),
            high=float(high),
            low=float(low),
            close=float(close),
            volume=float(volume),
            raw_close=float(raw),
        )
        for session, open_, high, low, close, volume, raw in zip(
            sessions, opens, highs, lows, closes, volumes, raws, strict=True
        )
    )
    reasons = tuple(part for part in meta.get(b"corp_action_reasons", b"").decode().split(",") if part)
    adjustment = meta.get(b"adjustment", b"split").decode()
    if adjustment not in {"split", "split_and_dividend"}:
        adjustment = "split"
    return BarSeries(
        ticker=meta.get(b"ticker", ticker.encode()).decode(),
        provider=meta.get(b"provider", b"cache").decode(),
        bars=bars,
        corp_action_suspect=meta.get(b"corp_action_suspect", b"false") == b"true",
        corp_action_reasons=reasons,
        adjustment=adjustment,  # type: ignore[arg-type]
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
