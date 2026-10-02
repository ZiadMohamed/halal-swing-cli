"""Pure entry signals shared by scan and the backtest.

The trigger math is the checklist's. A variant only switches which triggers,
whether a regime or earnings rule applies, and how the exit is planned.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from swing.brain.indicators import atr, atr_series, ema_series, rsi_series, sma
from swing.brain.setups import bo_rvol_signal, pb_ema_signal, rsi2_signal
from swing.config import SwingConfig
from swing.data.calendar import NyseCalendar
from swing.data.models import DailyBar

_TRIGGERS = {
    "BO_RVOL": bo_rvol_signal,
    "PB_EMA": pb_ema_signal,
    "RSI2_MR": rsi2_signal,
}


@dataclass(frozen=True)
class Variant:
    """One pre-registered book. Fields are the Appendix A switches, not a search."""

    name: str
    triggers: tuple[str, ...]
    rank: str
    seed: int
    exit: str
    slots: int
    max_position_frac: float | None
    risk: float
    regime: bool
    earnings: str
    entry_cap_atr: float | None
    trend_sma: int | None = None
    initial_atr: float = 1.5
    trail_atr: float = 3.0
    target_r: float = 2.0
    earnings_room: int = 3
    min_price: float = 0.0
    min_median_dollar_volume: float = 0.0
    min_sessions: int = 0


@dataclass(frozen=True)
class Candidate:
    ticker: str
    session: date
    triggers: tuple[str, ...]
    close: float
    atr: float
    momentum: float | None
    exit_by: date | None


def momentum(closes: list[float], *, lookback: int = 126, skip: int = 5) -> float | None:
    """close[t-skip] / close[t-lookback] - 1. The signal close is t."""
    need = lookback + 1
    if len(closes) < need or skip < 0 or lookback <= skip:
        return None
    recent = closes[-1 - skip]
    base = closes[-1 - lookback]
    if base <= 0 or recent <= 0:
        return None
    return recent / base - 1.0


class SignalTape:
    """One O(n) pass of the same trigger math, so a multi-year loop stays cheap."""

    def __init__(self, bars: tuple[DailyBar, ...], config: SwingConfig) -> None:
        self.bars = bars
        self.by_session = {bar.session: index for index, bar in enumerate(bars)}
        closes = [bar.close for bar in bars]
        highs = [bar.high for bar in bars]
        lows = [bar.low for bar in bars]
        volumes = [bar.volume for bar in bars]
        bo = config.setups.bo_rvol
        pb = config.setups.pb_ema
        rsi = config.setups.rsi2_mr
        self.atr = atr_series(highs, lows, closes, config.stops.atr_period)
        self.ema_trend = ema_series(closes, pb.ema_trend)
        self.ema_touch = ema_series(closes, pb.ema_touch)
        self.sma_bo = _sma_series(closes, bo.sma_period)
        self.sma_rsi = _sma_series(closes, rsi.sma_trend)
        self.rsi = rsi_series(closes, rsi.rsi_period)
        self.bo = _bo_flags(closes, highs, volumes, self.sma_bo, bo.breakout_lookback, bo.rvol_min)
        self.pb = _pb_flags(closes, lows, self.ema_trend, self.ema_touch)
        self.rsi_flag = _rsi_flags(closes, self.sma_rsi, self.rsi, rsi.rsi_max)
        self.momentum = _momentum_series(closes)

    def candidate(
        self,
        session: date,
        ticker: str,
        variant: Variant,
        calendar: NyseCalendar,
        earnings: tuple[date, ...] = (),
    ) -> Candidate | None:
        index = self.by_session.get(session)
        if index is None or index + 1 < variant.min_sessions:
            return None
        bar = self.bars[index]
        if not _liquid(self.bars, index, variant):
            return None
        if variant.trend_sma is not None:
            trend = _sma_at([item.close for item in self.bars], index, variant.trend_sma)
            if trend is None or bar.close <= trend:
                return None
        names = []
        if "BO_RVOL" in variant.triggers and self.bo[index]:
            names.append("BO_RVOL")
        if "PB_EMA" in variant.triggers and self.pb[index]:
            names.append("PB_EMA")
        if "RSI2_MR" in variant.triggers and self.rsi_flag[index]:
            names.append("RSI2_MR")
        if not names:
            return None
        reading = self.atr[index]
        if reading is None or reading <= 0:
            return None
        try:
            entry = calendar.shift_session(session, 1)
        except Exception:
            return None
        exit_by = _exit_by(variant, calendar, entry, earnings)
        if exit_by is _BLOCKED:
            return None
        return Candidate(
            ticker=ticker,
            session=session,
            triggers=tuple(names),
            close=bar.close,
            atr=reading,
            momentum=self.momentum[index],
            exit_by=None if exit_by is _NONE else exit_by,
        )


def matched_triggers(bars: tuple[DailyBar, ...] | list[DailyBar], config: SwingConfig, names: tuple[str, ...]) -> tuple[str, ...]:
    found = [name for name in names if _TRIGGERS[name](bars, config)]
    return tuple(found)


def regime_allows(spy: tuple[DailyBar, ...] | list[DailyBar] | None, period: int = 200) -> bool:
    if not spy:
        return False
    closes = [bar.close for bar in spy]
    average = sma(closes, period)
    if average is None:
        return False
    return closes[-1] > average


def candidate_for(
    ticker: str,
    bars: tuple[DailyBar, ...] | list[DailyBar],
    *,
    config: SwingConfig,
    variant: Variant,
    calendar: NyseCalendar,
    earnings: tuple[date, ...] = (),
) -> Candidate | None:
    """Signal at the last bar's close, or None when this variant does not enter."""
    if len(bars) < max(20, variant.min_sessions):
        return None
    if not _liquid(bars, len(bars) - 1, variant):
        return None
    if variant.trend_sma is not None:
        average = sma([bar.close for bar in bars], variant.trend_sma)
        if average is None or bars[-1].close <= average:
            return None
    triggers = matched_triggers(bars, config, variant.triggers)
    if not triggers:
        return None
    highs = [bar.high for bar in bars]
    lows = [bar.low for bar in bars]
    closes = [bar.close for bar in bars]
    reading = atr(highs, lows, closes, config.stops.atr_period)
    if reading is None or reading <= 0:
        return None
    signal = bars[-1].session
    try:
        entry = calendar.shift_session(signal, 1)
    except Exception:
        return None
    exit_by = _exit_by(variant, calendar, entry, earnings)
    if exit_by is _BLOCKED:
        return None
    return Candidate(
        ticker=ticker,
        session=signal,
        triggers=triggers,
        close=bars[-1].close,
        atr=reading,
        momentum=momentum(closes),
        exit_by=None if exit_by is _NONE else exit_by,
    )


class _Sentinel:
    pass


_BLOCKED = _Sentinel()
_NONE = _Sentinel()


def _exit_by(variant: Variant, calendar: NyseCalendar, entry: date, earnings: tuple[date, ...]):
    if variant.earnings == "off" or not earnings:
        return _NONE
    if _is_session_after_report(calendar, entry, earnings):
        return _BLOCKED
    upcoming = [day for day in earnings if day > entry]
    if variant.earnings == "through":
        return _NONE
    if variant.earnings == "blackout":
        if _in_v0_blackout(calendar, entry, earnings):
            return _BLOCKED
        return _NONE
    if variant.earnings != "exit" or not upcoming:
        return _NONE
    report = min(upcoming)
    exit_day = _session_before(calendar, report)
    if exit_day is None or exit_day < entry:
        return _BLOCKED
    if calendar.sessions_between(entry, exit_day) < variant.earnings_room:
        return _BLOCKED
    return exit_day


def _session_before(calendar: NyseCalendar, day: date) -> date | None:
    try:
        if calendar.is_session(day):
            return calendar.shift_session(day, -1)
        return calendar.session_on_or_before(day)
    except Exception:
        return None


def _is_session_after_report(calendar: NyseCalendar, entry: date, earnings: tuple[date, ...]) -> bool:
    for report in earnings:
        if report >= entry:
            continue
        try:
            nxt = calendar.shift_session(report, 1) if calendar.is_session(report) else _first_after(calendar, report)
        except Exception:
            continue
        if nxt == entry:
            return True
    return False


def _first_after(calendar: NyseCalendar, day: date) -> date | None:
    cursor = day
    for _ in range(10):
        cursor = cursor.fromordinal(cursor.toordinal() + 1)
        if calendar.is_session(cursor):
            return cursor
    return None


def _liquid(bars, index: int, variant: Variant) -> bool:
    price = bars[index].close
    if price < variant.min_price:
        return False
    floor = variant.min_median_dollar_volume
    if floor <= 0:
        return True
    if index < 19:
        return False
    dollars = sorted(bars[offset].close * bars[offset].volume for offset in range(index - 19, index + 1))
    median = (dollars[9] + dollars[10]) / 2
    return median >= floor


def _sma_series(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period < 1:
        return out
    running = 0.0
    for index, value in enumerate(values):
        running += value
        if index >= period:
            running -= values[index - period]
        if index >= period - 1:
            out[index] = running / period
    return out


def _sma_at(values: list[float], index: int, period: int) -> float | None:
    if period < 1 or index + 1 < period:
        return None
    window = values[index + 1 - period : index + 1]
    return sum(window) / period


def _bo_flags(closes, highs, volumes, sma_bo, lookback: int, rvol_min: float) -> list[bool]:
    flags = [False] * len(closes)
    for index in range(len(closes)):
        average = sma_bo[index]
        if average is None or index < lookback:
            continue
        volume_average = sum(volumes[index - lookback : index]) / lookback
        if volume_average <= 0:
            continue
        prior_high = max(highs[index - lookback : index])
        close = closes[index]
        if close > average and close > prior_high and volumes[index] / volume_average >= rvol_min:
            flags[index] = True
    return flags


def _pb_flags(closes, lows, ema_trend, ema_touch) -> list[bool]:
    flags = [False] * len(closes)
    for index, close in enumerate(closes):
        trend = ema_trend[index]
        touch = ema_touch[index]
        if trend is None or touch is None:
            continue
        flags[index] = close > trend and lows[index] <= touch and close > touch
    return flags


def _rsi_flags(closes, sma_rsi, rsi_values, rsi_max: float) -> list[bool]:
    flags = [False] * len(closes)
    for index, close in enumerate(closes):
        trend = sma_rsi[index]
        reading = rsi_values[index]
        if trend is None or reading is None:
            continue
        flags[index] = close > trend and reading < rsi_max
    return flags


def _momentum_series(closes: list[float], lookback: int = 126, skip: int = 5) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    for index in range(lookback, len(closes)):
        base = closes[index - lookback]
        recent = closes[index - skip]
        if base > 0 and recent > 0:
            out[index] = recent / base - 1.0
    return out


def _in_v0_blackout(calendar: NyseCalendar, entry: date, earnings: tuple[date, ...]) -> bool:
    from swing.brain.checklist import earnings_window

    for report in earnings:
        try:
            start, end = earnings_window(calendar, report, 2, 1)
        except Exception:
            continue
        if start <= entry <= end:
            return True
    return False
