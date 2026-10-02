"""Massive Basic daily bars. Adjusted OHLC is split-adjusted, not dividend-adjusted."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from swing.data.bars import cacheable, drop_invalid, through
from swing.data.cache import read_fresh_bars, write_bars
from swing.data.calendar import NyseCalendar
from swing.data.corp_actions import assess_corp_actions
from swing.data.errors import VendorError
from swing.data.http import endpoint_of, get_json, redact, strip_secrets
from swing.data.models import BarSeries, CorporateAction, DailyBar

_NY = ZoneInfo("America/New_York")
_BASE = "https://api.massive.com"
_Transport = Callable[[str, Mapping[str, str]], Any]


class MassiveBarProvider:
    """Daily aggregates from Massive Basic, plus splits and cash dividends."""

    def __init__(
        self,
        *,
        api_key: str,
        cache_dir,
        transport: _Transport | None = None,
        now: Callable[[], datetime] | None = None,
        calendar: NyseCalendar | None = None,
        base_url: str = _BASE,
    ) -> None:
        self._api_key = api_key
        self._cache_dir = cache_dir
        self._transport = transport or _default_transport
        self._now = now or (lambda: datetime.now(_NY))
        self._calendar = calendar or NyseCalendar()
        self._base = base_url.rstrip("/")

    def fetch_daily(self, ticker: str, lookback_sessions: int) -> BarSeries:
        symbol = ticker.strip().upper()
        now = self._now()
        cached = read_fresh_bars(self._cache_dir, symbol, lookback_sessions, now, self._calendar)
        if cached is not None:
            return cached
        start = now.date() - timedelta(days=lookback_sessions * 2 + 30)
        end = now.date()
        try:
            adjusted = self._aggs(symbol, start, end, adjusted=True)
            raw = self._aggs(symbol, start, end, adjusted=False)
            splits = self._pages(
                "/stocks/v1/splits",
                {"ticker": symbol, "limit": "1000", "sort": "execution_date.asc"},
            )
            dividends = self._pages("/stocks/v1/dividends", {"ticker": symbol, "limit": "1000"})
        except VendorError as exc:
            raise VendorError(
                redact(exc.detail, self._api_key), kind=exc.kind, endpoint=exc.endpoint, status=exc.status
            ) from None
        series = _series_from_massive(symbol, adjusted, raw, splits, dividends)
        series = replace(series, bars=through(series.bars, self._calendar.last_completed_session(now)))
        if not series.bars:
            raise VendorError("empty_bars", kind="upstream", endpoint="/v2/aggs")
        write_bars(self._cache_dir, cacheable(series, self._calendar.last_settled_session(now)))
        return series.sliced(lookback_sessions)

    def _aggs(self, symbol: str, start: date, end: date, *, adjusted: bool) -> list[dict[str, Any]]:
        path = f"/v2/aggs/ticker/{symbol}/range/1/day/{start.isoformat()}/{end.isoformat()}"
        params = {"adjusted": "true" if adjusted else "false", "sort": "asc", "limit": "50000"}
        return self._pages(path, params)

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


def _default_transport(url: str, headers: Mapping[str, str]) -> Any:
    return get_json(url, headers)


def _series_from_massive(
    ticker: str,
    adjusted_rows: list[dict[str, Any]],
    raw_rows: list[dict[str, Any]],
    split_rows: list[dict[str, Any]],
    dividend_rows: list[dict[str, Any]],
) -> BarSeries:
    raw_by_session = {}
    for row in raw_rows:
        session = _session(row.get("t"))
        if session is None:
            continue
        raw_by_session[session] = row
    bars: list[DailyBar] = []
    for row in adjusted_rows:
        session = _session(row.get("t"))
        raw = raw_by_session.get(session) if session is not None else None
        if session is None or raw is None:
            continue
        bars.append(
            DailyBar(
                session=session,
                open=_num(row.get("o")),
                high=_num(row.get("h")),
                low=_num(row.get("l")),
                close=_num(row.get("c")),
                volume=_num(row.get("v")),
                raw_close=_num(raw.get("c")),
            )
        )
    actions = _actions(split_rows, dividend_rows)
    ordered = drop_invalid(sorted(bars, key=lambda bar: bar.session))
    assessment = assess_corp_actions(ordered, actions, adjustment="split")
    return BarSeries(
        ticker=ticker,
        provider="massive",
        bars=ordered,
        corp_action_suspect=assessment.suspect,
        corp_action_reasons=assessment.reasons,
        adjustment="split",
    )


def _actions(split_rows: list[dict[str, Any]], dividend_rows: list[dict[str, Any]]) -> list[CorporateAction]:
    actions: list[CorporateAction] = []
    for row in split_rows:
        session = _iso_date(row.get("execution_date"))
        split_to = row.get("split_to")
        split_from = row.get("split_from")
        if session is None or split_to in (None, 0) or split_from in (None, 0):
            continue
        actions.append(
            CorporateAction(
                session=session,
                kind="split",
                split_to=float(split_to),
                split_from=float(split_from),
            )
        )
    for row in dividend_rows:
        session = _iso_date(row.get("ex_dividend_date"))
        amount = row.get("cash_amount")
        if session is None or amount is None:
            continue
        actions.append(CorporateAction(session=session, kind="dividend", amount=float(amount)))
    return actions


def _session(timestamp: object) -> date | None:
    if not isinstance(timestamp, (int, float)):
        return None
    moment = datetime.fromtimestamp(timestamp / 1000, tz=_NY)
    return moment.date()


def _iso_date(value: object) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    return date.fromisoformat(value[:10])


def _num(value: object) -> float:
    """Missing stays NaN so `drop_invalid` removes the row; never read as 0."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return math.nan
