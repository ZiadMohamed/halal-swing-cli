"""Finnhub earnings calendar (free tier). This module does not request OHLC.

Only `/calendar/earnings` is called. Dividend, split, and candle endpoints are
premium on Finnhub and return 403 for a free key, so they are never requested.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from swing.data.errors import MissingApiKeyError, VendorError
from swing.data.http import get_json, redact
from swing.data.models import EarningsEvent, EarningsHour

_NY = ZoneInfo("America/New_York")
_BASE = "https://finnhub.io/api/v1"
_HOURS = frozenset({"bmo", "amc", "dmh"})
_PAST_DAYS = 5
_FORWARD_DAYS = 35
_Transport = Callable[[str, Mapping[str, str]], Any]


class FinnhubEvents:
    """Earnings announcement dates for one ticker, from today-5 to today+35."""

    def __init__(
        self,
        *,
        api_key: str,
        transport: _Transport | None = None,
        today: date | None = None,
        base_url: str = _BASE,
    ) -> None:
        self._api_key = api_key.strip()
        self._transport = transport or _default_transport
        self._today = today
        self._base = base_url.rstrip("/")

    def window(self) -> tuple[date, date]:
        today = self._today if self._today is not None else datetime.now(_NY).date()
        return today - timedelta(days=_PAST_DAYS), today + timedelta(days=_FORWARD_DAYS)

    def earnings_calendar(self, ticker: str) -> tuple[EarningsEvent, ...]:
        symbol = ticker.strip().upper()
        start, end = self.window()
        path = "/calendar/earnings"
        payload = self._get(path, {"symbol": symbol, "from": start.isoformat(), "to": end.isoformat()})
        rows = payload.get("earningsCalendar") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise VendorError("earningsCalendar missing", kind="bad_payload", endpoint=path)
        events: list[EarningsEvent] = []
        for row in rows:
            if not isinstance(row, dict) or row.get("symbol") != symbol:
                continue
            report_date = _date(row.get("date"))
            if report_date is None:
                continue
            events.append(
                EarningsEvent(
                    ticker=symbol,
                    report_date=report_date,
                    hour=_hour(row.get("hour")),
                    quarter=_int(row.get("quarter")),
                    year=_int(row.get("year")),
                    source="finnhub",
                )
            )
        events.sort(key=lambda item: item.report_date)
        return tuple(events)

    def _get(self, path: str, params: Mapping[str, str]) -> Any:
        if not self._api_key:
            raise MissingApiKeyError("FINNHUB_API_KEY")
        url = f"{self._base}{path}?{urlencode(params)}"
        headers = {"X-Finnhub-Token": self._api_key, "Accept": "application/json"}
        try:
            payload = self._transport(url, headers)
        except VendorError as exc:
            raise VendorError(
                redact(exc.detail, self._api_key),
                kind=exc.kind,
                endpoint=exc.endpoint or path,
                status=exc.status,
            ) from None
        except Exception as exc:  # noqa: BLE001 — vendor boundary
            detail = redact(f"{type(exc).__name__}:{exc}", self._api_key)
            raise VendorError(detail, kind="upstream", endpoint=path) from None
        if isinstance(payload, dict) and payload.get("error"):
            raise VendorError(redact(str(payload["error"]), self._api_key), kind="bad_payload", endpoint=path)
        return payload


def _default_transport(url: str, headers: Mapping[str, str]) -> Any:
    return get_json(url, headers)


def _date(value: object) -> date | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _hour(value: object) -> EarningsHour:
    if isinstance(value, str) and value in _HOURS:
        return value  # type: ignore[return-value]
    return "unknown"


def _int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)
