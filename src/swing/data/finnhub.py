"""Finnhub earnings and dividend calendars. This module does not request OHLC."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from swing.data.errors import MissingApiKeyError, VendorError
from swing.data.http import get_json, redact
from swing.data.models import DividendEvent, EarningsEvent, EarningsHour

_NY = ZoneInfo("America/New_York")
_BASE = "https://finnhub.io/api/v1"
_HOURS = frozenset({"bmo", "amc", "dmh"})
_Transport = Callable[[str, Mapping[str, str]], Any]


class FinnhubEvents:
    """Earnings announcement dates and cash dividend ex-dates for one ticker."""

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

    def earnings_calendar(self, ticker: str) -> tuple[EarningsEvent, ...]:
        symbol = ticker.strip().upper()
        start, end = self._window()
        payload = self._get("/calendar/earnings", {"symbol": symbol, "from": start.isoformat(), "to": end.isoformat()})
        if not isinstance(payload, dict):
            raise VendorError("invalid_payload")
        rows = payload.get("earningsCalendar")
        if not isinstance(rows, list):
            raise VendorError("invalid_payload")
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
                )
            )
        events.sort(key=lambda item: item.report_date)
        return tuple(events)

    def dividend_calendar(self, ticker: str) -> tuple[DividendEvent, ...]:
        symbol = ticker.strip().upper()
        start, end = self._window()
        payload = self._get("/stock/dividend", {"symbol": symbol, "from": start.isoformat(), "to": end.isoformat()})
        rows = _dividend_rows(payload)
        events: list[DividendEvent] = []
        for row in rows:
            if row.get("symbol") not in (None, symbol):
                continue
            ex_date = _date(row.get("date") or row.get("ex_dividend_date"))
            amount = row.get("amount")
            if amount is None:
                amount = row.get("adjustedAmount")
            if ex_date is None or not isinstance(amount, (int, float)):
                continue
            currency = row.get("currency")
            events.append(
                DividendEvent(
                    ticker=symbol,
                    ex_date=ex_date,
                    amount=float(amount),
                    currency=currency if isinstance(currency, str) and currency else "USD",
                    pay_date=_date(row.get("payDate") or row.get("pay_date")),
                    frequency=_text(row.get("freq") or row.get("frequency")),
                )
            )
        events.sort(key=lambda item: item.ex_date)
        return tuple(events)

    def _window(self) -> tuple[date, date]:
        today = self._today if self._today is not None else datetime.now(_NY).date()
        return today - timedelta(days=30), today + timedelta(days=180)

    def _get(self, path: str, params: Mapping[str, str]) -> Any:
        if not self._api_key:
            raise MissingApiKeyError("FINNHUB_API_KEY")
        url = f"{self._base}{path}?{urlencode(params)}"
        headers = {"X-Finnhub-Token": self._api_key, "Accept": "application/json"}
        try:
            payload = self._transport(url, headers)
        except VendorError as exc:
            raise VendorError(redact(str(exc), self._api_key)) from None
        except Exception as exc:  # noqa: BLE001 — vendor boundary
            raise VendorError(redact(f"{type(exc).__name__}:{exc}", self._api_key)) from None
        if isinstance(payload, dict) and payload.get("error"):
            raise VendorError(redact(str(payload["error"]), self._api_key))
        return payload


def _default_transport(url: str, headers: Mapping[str, str]) -> Any:
    return get_json(url, headers)


def _dividend_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        rows = payload.get("data")
        if rows is None:
            rows = payload.get("results")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    raise VendorError("invalid_payload")


def _date(value: object) -> date | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    return date.fromisoformat(value[:10])


def _hour(value: object) -> EarningsHour:
    if isinstance(value, str) and value in _HOURS:
        return value  # type: ignore[return-value]
    return "unknown"


def _int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _text(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return None
