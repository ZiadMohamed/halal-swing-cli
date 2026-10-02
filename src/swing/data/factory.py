"""Build vendors from config. Finnhub is never a bars provider.

Earnings: Finnhub `/calendar/earnings` when FINNHUB_API_KEY is set. When the
key is missing or the call fails, the yfinance calendar and earnings dates are
the fallback, and they count only when they give a dated next report. ETFs
have no earnings and skip the lookup. Dividends are optional yfinance data and
never change `events_known`.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from swing.config import SwingConfig
from swing.data.calendar import NyseCalendar
from swing.data.errors import DataError, MissingApiKeyError
from swing.data.finnhub import FinnhubEvents
from swing.data.massive import MassiveBarProvider
from swing.data.models import DEFAULT_LOOKBACK_SESSIONS, BarSeries, DividendEvent, EarningsEvent, MarketData
from swing.data.yahoo_events import YahooEvents, has_next_report
from swing.data.yfinance_bars import YFinanceBarProvider
from swing.paths import bars_cache_dir

_NY = ZoneInfo("America/New_York")
_LOG = logging.getLogger(__name__)


class _MissingKeyBars:
    def __init__(self, env_name: str) -> None:
        self._env_name = env_name

    def fetch_daily(self, ticker: str, lookback_sessions: int) -> BarSeries:
        del ticker, lookback_sessions
        raise MissingApiKeyError(self._env_name)


def build_bar_provider(
    config: SwingConfig,
    env: Mapping[str, str],
    cache_dir: Path,
    *,
    now=None,
):
    name = config.data.bars_provider
    if name == "finnhub" or name not in {"yfinance", "massive"}:
        raise ValueError("Finnhub is events only and cannot provide OHLC")
    if name == "yfinance":
        return YFinanceBarProvider(cache_dir=cache_dir, now=now)
    key = env.get("MASSIVE_API_KEY", "").strip()
    if not key:
        return _MissingKeyBars("MASSIVE_API_KEY")
    return MassiveBarProvider(api_key=key, cache_dir=cache_dir, now=now)


def build_event_provider(config: SwingConfig, env: Mapping[str, str], *, today=None) -> FinnhubEvents:
    if config.data.events_provider != "finnhub":
        raise ValueError("events provider must be finnhub")
    return FinnhubEvents(api_key=env.get("FINNHUB_API_KEY", ""), today=today)


def load_market_data(
    ticker: str,
    config: SwingConfig,
    *,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
    cache_dir: Path | None = None,
    lookback_sessions: int = DEFAULT_LOOKBACK_SESSIONS,
    bars=None,
    events=None,
    yahoo: YahooEvents | None = None,
    calendar: NyseCalendar | None = None,
    with_events: bool = True,
) -> MarketData:
    """Fetch bars, events, and the next open. Vendor failures stay on the bundle."""
    environ: Mapping[str, str] = os.environ if env is None else env
    clock = now if now is not None else datetime.now(_NY)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=_NY)
    today = clock.astimezone(_NY).date()
    cache = cache_dir if cache_dir is not None else bars_cache_dir(env=environ)
    cal = calendar or NyseCalendar()
    bar_provider = bars if bars is not None else build_bar_provider(config, environ, cache, now=lambda: clock)
    event_provider = events if events is not None else build_event_provider(config, environ, today=today)
    yahoo_events = yahoo if yahoo is not None else YahooEvents(today=today)
    symbol = ticker.strip().upper()

    errors: list[str] = []
    expected: date | None = None
    try:
        expected = cal.last_completed_session(clock)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"vendor_error:calendar:{type(exc).__name__}")

    series: BarSeries | None = None
    try:
        series = bar_provider.fetch_daily(symbol, lookback_sessions)
    except DataError as exc:
        errors.append(_error_text(exc, config.data.bars_provider))
    except Exception as exc:  # noqa: BLE001 — keep analyze printable
        errors.append(f"vendor_error:{config.data.bars_provider}:{type(exc).__name__}")

    instrument = _instrument(series, yahoo_events, symbol) if series is not None else None

    earnings: tuple[EarningsEvent, ...] = ()
    earnings_source: str | None = None
    events_known = False
    if instrument == "ETF":
        events_known = True
        earnings_source = "not_applicable"
    elif with_events:
        try:
            earnings = tuple(event_provider.earnings_calendar(symbol))
            events_known = True
            earnings_source = "finnhub"
        except DataError as exc:
            errors.append(_error_text(exc, "finnhub"))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"vendor_error:finnhub:{type(exc).__name__}")
        if not events_known:
            earnings, events_known, earnings_source = _yahoo_earnings(yahoo_events, symbol, today, errors)

    dividends: tuple[DividendEvent, ...] = ()
    if with_events:
        try:
            dividends = tuple(yahoo_events.dividends(symbol))
        except Exception as exc:  # noqa: BLE001 — optional data, never blocks
            _LOG.info("dividends unavailable for %s: %s", symbol, type(exc).__name__)

    next_open: str | None = None
    try:
        next_open = cal.next_open(clock.isoformat())
    except Exception as exc:  # noqa: BLE001
        errors.append(f"vendor_error:calendar:{type(exc).__name__}")

    if series is not None and (events_known or not with_events):
        status = "ok"
    elif series is not None:
        status = "partial"
    else:
        status = "error"
    return MarketData(
        ticker=symbol,
        status=status,
        bars_provider=config.data.bars_provider,
        events_provider=config.data.events_provider,
        bars=series,
        earnings=earnings,
        dividends=dividends,
        next_open=next_open,
        errors=tuple(errors),
        events_known=events_known,
        instrument_type=instrument,
        earnings_source=earnings_source,
        last_completed_session=expected,
    )


def _instrument(series: BarSeries, yahoo: YahooEvents, symbol: str) -> str | None:
    """ETF or EQUITY from yfinance metadata. Anything else, or unknown, is None (strict)."""
    value = series.instrument_type
    if value is None:
        try:
            value = yahoo.instrument_type(symbol)
        except Exception as exc:  # noqa: BLE001 — unknown type keeps strict earnings
            _LOG.info("instrument type unavailable for %s: %s", symbol, type(exc).__name__)
            return None
    text = (value or "").strip().upper()
    return text if text in {"EQUITY", "ETF"} else None


def _yahoo_earnings(
    yahoo: YahooEvents,
    symbol: str,
    today: date,
    errors: list[str],
) -> tuple[tuple[EarningsEvent, ...], bool, str | None]:
    try:
        found = tuple(yahoo.earnings(symbol))
    except DataError as exc:
        errors.append(_error_text(exc, "yfinance"))
        return (), False, None
    except Exception as exc:  # noqa: BLE001
        errors.append(f"vendor_error:yfinance:{type(exc).__name__}")
        return (), False, None
    if not has_next_report(found, today):
        errors.append("earnings_unknown:yfinance:no dated next report")
        return found, False, None
    return found, True, "yfinance"


def _error_text(exc: DataError, source: str) -> str:
    if isinstance(exc, MissingApiKeyError):
        return f"missing_api_key:{exc.env_name}"
    return f"vendor_error:{source}:{exc}"
