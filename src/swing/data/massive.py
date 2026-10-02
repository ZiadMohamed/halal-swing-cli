"""Massive Basic daily bars.

One adjusted aggregate backfill per ticker, one grouped daily call per missing
session for the universe, and one splits list per day. Raw aggregates and
dividend endpoints are not called.
"""

from __future__ import annotations

import json
import math
import sys
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from swing.data.bars import cacheable, is_valid, sanitize
from swing.data.cache import read_bars, read_fresh_bars, write_bars
from swing.data.calendar import NyseCalendar
from swing.data.errors import VendorError
from swing.data.http import endpoint_of, get_json, redact, strip_secrets
from swing.data.models import BarSeries, DailyBar
from swing.data.throttle import RateLimiter

_NY = ZoneInfo("America/New_York")
_BASE = "https://api.massive.com"
_BACKFILL_DAYS = 365 * 2
_Transport = Callable[[str, Mapping[str, str]], Any]


class MassiveBarProvider:
    """Adjusted daily bars from Massive Basic, throttled to 5 calls a minute."""

    def __init__(
        self,
        *,
        api_key: str,
        cache_dir,
        transport: _Transport | None = None,
        now: Callable[[], datetime] | None = None,
        calendar: NyseCalendar | None = None,
        limiter: RateLimiter | None = None,
        base_url: str = _BASE,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        self._api_key = api_key
        self._cache_dir = Path(cache_dir)
        self._transport = transport or _default_transport
        self._now = now or (lambda: datetime.now(_NY))
        self._calendar = calendar or NyseCalendar()
        self._limiter = limiter or RateLimiter(5)
        self._base = base_url.rstrip("/")
        self._progress = progress or _stderr

    def fetch_daily(self, ticker: str, lookback_sessions: int) -> BarSeries:
        symbol = ticker.strip().upper()
        now = self._now()
        cached = read_fresh_bars(self._cache_dir, symbol, lookback_sessions, now, self._calendar)
        if cached is not None:
            return cached
        self._limiter.acquire()
        series = self._backfill(symbol, now)
        splits = self._split_sessions(self._calendar.last_completed_session(now))
        return self._store(series, splits.get(symbol, set()), lookback_sessions, now)

    def load_universe(self, tickers: list[str], lookback_sessions: int) -> dict[str, BarSeries]:
        """Fill every ticker from cache, grouped dailies, and throttled backfill.

        A warm cache plus a splits list already stored for the day makes no
        HTTP call. A missing session is one grouped call for the whole universe.
        """
        now = self._now()
        last = self._calendar.last_completed_session(now)
        symbols = [ticker.strip().upper() for ticker in tickers]
        loaded: dict[str, BarSeries] = {}
        backfill: list[str] = []
        for symbol in symbols:
            cached = read_bars(self._cache_dir, symbol)
            if cached is None or len(cached.bars) < lookback_sessions or _needs_backfill(cached, last, self._calendar):
                backfill.append(symbol)
            else:
                loaded[symbol] = cached
        total = len(backfill)
        for index, symbol in enumerate(backfill, start=1):
            self._progress(f"backfill {index}/{total} {symbol}")
            self._limiter.acquire()
            loaded[symbol] = self._backfill(symbol, now)

        missing: set[date] = set()
        for series in loaded.values():
            if not series.bars:
                continue
            missing.update(self._calendar.sessions_after(series.bars[-1].session, last))
        for session in sorted(missing):
            self._limiter.acquire()
            grouped = self._grouped(session)
            for symbol, series in list(loaded.items()):
                bar = grouped.get(symbol)
                if bar is None or any(existing.session == bar.session for existing in series.bars):
                    continue
                loaded[symbol] = replace(series, bars=tuple(sorted((*series.bars, bar), key=lambda item: item.session)))

        splits = self._split_sessions(last)
        stored: dict[str, BarSeries] = {}
        for symbol, series in loaded.items():
            stored[symbol] = self._store(series, splits.get(symbol, set()), lookback_sessions, now)
        return stored

    def _backfill(self, symbol: str, now: datetime) -> BarSeries:
        start = now.date() - timedelta(days=_BACKFILL_DAYS)
        end = now.date()
        try:
            rows = self._aggs(symbol, start, end)
        except VendorError as exc:
            raise VendorError(
                redact(exc.detail, self._api_key), kind=exc.kind, endpoint=exc.endpoint, status=exc.status
            ) from None
        bars = [_bar_from_row(row) for row in rows]
        return BarSeries(
            ticker=symbol,
            provider="massive",
            bars=tuple(bar for bar in bars if bar is not None),
            corp_action_suspect=False,
            corp_action_reasons=(),
            adjustment="split",
        )

    def _store(self, series: BarSeries, split_sessions: set[date], lookback: int, now: datetime) -> BarSeries:
        last = self._calendar.last_completed_session(now)
        cleaned, reasons = sanitize(series.bars, last_session=last, split_sessions=split_sessions)
        if not cleaned:
            raise VendorError("empty_bars", kind="upstream", endpoint="/v2/aggs")
        stored = replace(series, bars=cleaned, corp_action_suspect=bool(reasons), corp_action_reasons=reasons)
        write_bars(self._cache_dir, cacheable(stored, self._calendar.last_settled_session(now)))
        return stored.sliced(lookback)

    def _aggs(self, symbol: str, start: date, end: date) -> list[dict[str, Any]]:
        path = f"/v2/aggs/ticker/{symbol}/range/1/day/{start.isoformat()}/{end.isoformat()}"
        return self._pages(path, {"adjusted": "true", "sort": "asc", "limit": "50000"})

    def _grouped(self, session: date) -> dict[str, DailyBar]:
        path = f"/v2/aggs/grouped/locale/us/market/stocks/{session.isoformat()}"
        payload = self._get(path, {"adjusted": "true"})
        return parse_grouped_daily(payload, session)

    def _split_sessions(self, day: date) -> dict[str, set[date]]:
        path = self._cache_dir / "splits.json"
        cached = _read_splits(path, day)
        if cached is not None:
            return cached
        self._limiter.acquire()
        try:
            rows = self._pages("/stocks/v1/splits", {"limit": "1000", "sort": "execution_date.desc"})
        except VendorError as exc:
            raise VendorError(
                redact(exc.detail, self._api_key), kind=exc.kind, endpoint=exc.endpoint, status=exc.status
            ) from None
        found: dict[str, set[date]] = {}
        for row in rows:
            symbol = row.get("ticker")
            session = _iso_date(row.get("execution_date"))
            if not isinstance(symbol, str) or session is None:
                continue
            found.setdefault(symbol.upper(), set()).add(session)
        _write_splits(path, day, found)
        return found

    def _pages(self, path: str, params: Mapping[str, str]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        url: str | None = None
        for _ in range(20):
            payload = self._get(url if url is not None else path, {} if url is not None else params)
            if not isinstance(payload, dict):
                raise VendorError("payload is not an object", kind="bad_payload", endpoint=path)
            status = payload.get("status")
            if status not in (None, "OK", "DELAYED"):
                raise VendorError(f"status_{status}", kind="bad_payload", endpoint=path)
            chunk = payload.get("results") or []
            if not isinstance(chunk, list):
                raise VendorError("results is not a list", kind="bad_payload", endpoint=path)
            rows.extend(row for row in chunk if isinstance(row, dict))
            nxt = payload.get("next_url") or ""
            if not isinstance(nxt, str) or not nxt:
                break
            url = strip_secrets(nxt)
        return rows

    def _get(self, path_or_url: str, params: Mapping[str, str]) -> Any:
        if path_or_url.startswith("http"):
            url = strip_secrets(path_or_url)
        else:
            query = urlencode(params)
            url = f"{self._base}{path_or_url}"
            if query:
                url = f"{url}?{query}"
        headers = {"Authorization": f"Bearer {self._api_key}", "Accept": "application/json"}
        try:
            return self._transport(url, headers)
        except VendorError:
            raise
        except Exception as exc:  # noqa: BLE001 — vendor boundary
            raise VendorError(
                redact(f"{type(exc).__name__}:{exc}", self._api_key), kind="upstream", endpoint=endpoint_of(url)
            ) from None


def parse_grouped_daily(payload: Any, session: date) -> dict[str, DailyBar]:
    """Map a grouped-daily payload to valid bars for that session."""
    if not isinstance(payload, dict):
        raise VendorError("payload is not an object", kind="bad_payload", endpoint="/v2/aggs/grouped")
    status = payload.get("status")
    if status not in (None, "OK", "DELAYED"):
        raise VendorError(f"status_{status}", kind="bad_payload", endpoint="/v2/aggs/grouped")
    rows = payload.get("results") or []
    if not isinstance(rows, list):
        raise VendorError("results is not a list", kind="bad_payload", endpoint="/v2/aggs/grouped")
    found: dict[str, DailyBar] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = row.get("T")
        if not isinstance(symbol, str) or not symbol:
            continue
        bar = _bar_from_row(row, session=session)
        if bar is not None and is_valid(bar):
            found[symbol.upper()] = bar
    return found


def _bar_from_row(row: Mapping[str, Any], session: date | None = None) -> DailyBar | None:
    day = session if session is not None else _session(row.get("t"))
    if day is None:
        return None
    close = _num(row.get("c"))
    return DailyBar(
        session=day,
        open=_num(row.get("o")),
        high=_num(row.get("h")),
        low=_num(row.get("l")),
        close=close,
        volume=_num(row.get("v")),
        raw_close=close,
    )


def _default_transport(url: str, headers: Mapping[str, str]) -> Any:
    return get_json(url, headers)


def _needs_backfill(series: BarSeries, last: date, calendar: NyseCalendar) -> bool:
    """A long gap is a backfill. One or a few missing sessions use grouped daily."""
    if not series.bars:
        return True
    return len(calendar.sessions_after(series.bars[-1].session, last)) > 5


def _stderr(message: str) -> None:
    print(message, file=sys.stderr)


def _session(timestamp: object) -> date | None:
    if not isinstance(timestamp, (int, float)) or isinstance(timestamp, bool):
        return None
    moment = datetime.fromtimestamp(timestamp / 1000, tz=_NY)
    return moment.date()


def _iso_date(value: object) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    return date.fromisoformat(value[:10])


def _num(value: object) -> float:
    """Missing stays NaN so invalid rows are dropped. Never read as 0."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return math.nan


def _read_splits(path: Path, day: date) -> dict[str, set[date]] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("day") != day.isoformat():
        return None
    rows = payload.get("splits")
    if not isinstance(rows, dict):
        return None
    found: dict[str, set[date]] = {}
    for symbol, sessions in rows.items():
        if not isinstance(symbol, str) or not isinstance(sessions, list):
            continue
        days = {date.fromisoformat(item) for item in sessions if isinstance(item, str)}
        if days:
            found[symbol] = days
    return found


def _write_splits(path: Path, day: date, splits: dict[str, set[date]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "day": day.isoformat(),
        "splits": {symbol: sorted(item.isoformat() for item in sessions) for symbol, sessions in splits.items()},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
