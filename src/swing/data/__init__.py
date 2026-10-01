"""Market data: bars, Finnhub events, the NYSE calendar, and the Parquet cache."""

from swing.data.calendar import NyseCalendar
from swing.data.errors import DataError, MissingApiKeyError, VendorError
from swing.data.factory import build_bar_provider, build_event_provider, load_market_data
from swing.data.models import (
    DEFAULT_LOOKBACK_SESSIONS,
    BarSeries,
    DailyBar,
    DividendEvent,
    EarningsEvent,
    MarketData,
)
from swing.data.ports import (
    BarProvider,
    CalendarProvider,
    EventProvider,
    UnimplementedBars,
    UnimplementedCalendar,
    UnimplementedEvents,
)

__all__ = [
    "DEFAULT_LOOKBACK_SESSIONS",
    "BarProvider",
    "BarSeries",
    "CalendarProvider",
    "DailyBar",
    "DataError",
    "DividendEvent",
    "EarningsEvent",
    "EventProvider",
    "MarketData",
    "MissingApiKeyError",
    "NyseCalendar",
    "UnimplementedBars",
    "UnimplementedCalendar",
    "UnimplementedEvents",
    "VendorError",
    "build_bar_provider",
    "build_event_provider",
    "load_market_data",
]
