"""Bars, events, and the bundle Chat 3 reads. No setup math lives here."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import Literal

Adjustment = Literal["split", "split_and_dividend"]
EarningsHour = Literal["bmo", "amc", "dmh", "unknown"]
MarketStatus = Literal["ok", "partial", "error"]
InstrumentType = Literal["EQUITY", "ETF"]

# Enough sessions for SMA(200) plus warmup. Not a hashed policy field.
DEFAULT_LOOKBACK_SESSIONS = 320


@dataclass(frozen=True)
class DailyBar:
    """One NYSE session. OHLC is the split-adjusted series used for indicators."""

    session: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    raw_close: float


@dataclass(frozen=True)
class CorporateAction:
    session: date
    kind: Literal["split", "dividend"]
    split_to: float | None = None
    split_from: float | None = None
    amount: float | None = None


@dataclass(frozen=True)
class CorpActionAssessment:
    suspect: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class BarSeries:
    """Oldest-first daily bars for one ticker.

    `corp_action_suspect` is true when the adjustment does not line up with the
    vendor's own unadjusted series or with the corporate actions it reported.
    Chat 3 should refuse a suspect series instead of running indicators on it.

    `reconstructed` is true when the last bar was rebuilt from 1-hour
    regular-session bars because the vendor's daily row was missing or not
    finite. A reconstructed bar is never cached.
    """

    ticker: str
    provider: str
    bars: tuple[DailyBar, ...]
    corp_action_suspect: bool
    corp_action_reasons: tuple[str, ...]
    adjustment: Adjustment
    reconstructed: bool = False
    instrument_type: str | None = None

    def sliced(self, lookback: int) -> BarSeries:
        if lookback < 1:
            raise ValueError("lookback_sessions must be positive")
        return replace(self, bars=self.bars[-lookback:])


@dataclass(frozen=True)
class EarningsEvent:
    """Announcement date for the earnings blackout.

    `report_date` is T. Chat 3 applies T minus `earnings.blackout_before_days`
    through T plus `earnings.blackout_after_days` on NYSE sessions when
    `earnings.strict` is true. This object does not decide NO_TRADE.

    `hour` is `bmo` before the open, `amc` after the close, `dmh` during the
    session, or `unknown`.
    """

    ticker: str
    report_date: date
    hour: EarningsHour
    quarter: int | None = None
    year: int | None = None
    source: str | None = None


@dataclass(frozen=True)
class DividendEvent:
    """Cash distribution on the ex-dividend date. Optional data; never required.

    `amount` is cash per share when the source gives it, else None. Chat 3
    compares a known amount with the prior close. This object does not decide.
    """

    ticker: str
    ex_date: date
    amount: float | None
    currency: str  # vendor label only; plan money is USD and v0 does not convert
    pay_date: date | None = None
    frequency: str | None = None


@dataclass(frozen=True)
class MarketData:
    """Everything the checklist may read from the data layer.

    Research headlines are not on this object. Do not pass a ResearchResult
    into indicator code.

    `events_known` describes the earnings calendar only. Dividends never
    change it. `last_completed_session` is the NYSE session the signal bar
    must equal; None skips the freshness check (fixtures only).
    """

    ticker: str
    status: MarketStatus
    bars_provider: str | None
    events_provider: str | None
    bars: BarSeries | None
    earnings: tuple[EarningsEvent, ...]
    dividends: tuple[DividendEvent, ...]
    next_open: str | None
    errors: tuple[str, ...]
    events_known: bool = True
    instrument_type: InstrumentType | None = None
    earnings_source: str | None = None
    last_completed_session: date | None = None
