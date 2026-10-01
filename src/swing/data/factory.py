"""Build vendors from config. Finnhub is never a bars provider."""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from swing.config import SwingConfig
from swing.data.calendar import NyseCalendar
from swing.data.errors import DataError, MissingApiKeyError
from swing.data.finnhub import FinnhubEvents
from swing.data.massive import MassiveBarProvider
from swing.data.models import DEFAULT_LOOKBACK_SESSIONS, BarSeries, DividendEvent, EarningsEvent, MarketData
from swing.data.yfinance_bars import YFinanceBarProvider
from swing.paths import bars_cache_dir

_NY = ZoneInfo("America/New_York")


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
    calendar: NyseCalendar | None = None,
) -> MarketData:
    """Fetch bars, events, and the next open. Vendor failures stay on the bundle.

    The returned object is the only market input Chat 3 should give the brain.
    """
    environ: Mapping[str, str] = os.environ if env is None else env
    clock = now if now is not None else datetime.now(_NY)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=_NY)
    cache = cache_dir if cache_dir is not None else bars_cache_dir(env=environ)
    cal = calendar or NyseCalendar()
    bar_provider = bars if bars is not None else build_bar_provider(
        config, environ, cache, now=lambda: clock
    )
    event_provider = events if events is not None else build_event_provider(config, environ, today=clock.date())

    errors: list[str] = []
    series: BarSeries | None = None
    try:
        series = bar_provider.fetch_daily(ticker, lookback_sessions)
    except DataError as exc:
        errors.append(_error_text(exc, config.data.bars_provider))
    except Exception as exc:  # noqa: BLE001 — keep analyze printable
        errors.append(f"vendor_error:{config.data.bars_provider}:{type(exc).__name__}")

    earnings: tuple[EarningsEvent, ...] = ()
    dividends: tuple[DividendEvent, ...] = ()
    events_failed = False
    try:
        earnings = tuple(event_provider.earnings_calendar(ticker))
    except DataError as exc:
        events_failed = True
        errors.append(_error_text(exc, "finnhub"))
    except Exception as exc:  # noqa: BLE001
        events_failed = True
        errors.append(f"vendor_error:finnhub:{type(exc).__name__}")
    if not events_failed:
        try:
            dividends = tuple(event_provider.dividend_calendar(ticker))
        except DataError as exc:
            events_failed = True
            message = _error_text(exc, "finnhub")
            if message not in errors:
                errors.append(message)
        except Exception as exc:  # noqa: BLE001
            events_failed = True
            errors.append(f"vendor_error:finnhub:{type(exc).__name__}")

    next_open: str | None = None
    try:
        next_open = cal.next_open(clock.isoformat())
    except Exception as exc:  # noqa: BLE001
        errors.append(f"vendor_error:calendar:{type(exc).__name__}")

    if series is not None and not events_failed:
        status = "ok"
    elif series is not None:
        status = "partial"
    else:
        status = "error"
    return MarketData(
        ticker=ticker.strip().upper(),
        status=status,
        bars_provider=config.data.bars_provider,
        events_provider=config.data.events_provider,
        bars=series,
        earnings=earnings,
        dividends=dividends,
        next_open=next_open,
        errors=tuple(errors),
        events_known=not events_failed,
    )


def _error_text(exc: DataError, source: str) -> str:
    if isinstance(exc, MissingApiKeyError):
        return f"missing_api_key:{exc.env_name}"
    return f"vendor_error:{source}:{exc}"
