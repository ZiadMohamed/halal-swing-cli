"""Data ports.

Finnhub implements EventProvider only. Bars come from yfinance or Massive.
Concrete types live in swing.data.models. Chat 3 should read MarketData.
"""

from __future__ import annotations

from typing import Protocol


class BarProvider(Protocol):
    """Daily OHLCV. Implementations: yfinance (prototype) and Massive. Not Finnhub."""

    def fetch_daily(self, ticker: str, lookback_sessions: int) -> object:
        """Return split-adjusted bars plus a corp-action suspect flag. Chat 2."""
        ...


class EventProvider(Protocol):
    """Earnings and dividend calendars. Finnhub only. Do not request OHLC here."""

    def earnings_calendar(self, ticker: str) -> object:
        """Return earnings dates used for the T-2..T+1 blackout. Chat 2."""
        ...

    def dividend_calendar(self, ticker: str) -> object:
        """Return ex-div dates and cash amounts. Chat 2."""
        ...


class CalendarProvider(Protocol):
    """NYSE session clock, including holidays and early closes."""

    def next_open(self, after_iso: str) -> str:
        """Return the next NYSE open as an ISO timestamp in America/New_York. Chat 2."""
        ...


class UnimplementedBars:
    def fetch_daily(self, ticker: str, lookback_sessions: int) -> object:
        raise NotImplementedError("BarProvider is not installed in the skeleton. Chat 2 wires yfinance and Massive.")


class UnimplementedEvents:
    def earnings_calendar(self, ticker: str) -> object:
        raise NotImplementedError("Finnhub events are not installed in the skeleton. Chat 2.")

    def dividend_calendar(self, ticker: str) -> object:
        raise NotImplementedError("Finnhub events are not installed in the skeleton. Chat 2.")


class UnimplementedCalendar:
    def next_open(self, after_iso: str) -> str:
        raise NotImplementedError("NYSE calendar is not installed in the skeleton. Chat 2.")
