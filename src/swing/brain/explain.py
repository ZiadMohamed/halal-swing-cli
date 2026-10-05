"""Plain readings for the three setups.

The checklist still decides. These lines only say what the prices and the
indicators were, in the same definitions the signals use.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from swing.brain.indicators import atr, ema, rsi, sma
from swing.config import SwingConfig
from swing.data.calendar import NyseCalendar
from swing.data.models import DailyBar, MarketData


def unchecked_setups() -> tuple[str, ...]:
    return (
        "Breakout: not checked. No usable daily prices.",
        "Pullback: not checked. No usable daily prices.",
        "Two-day dip: not checked. No usable daily prices.",
    )


def describe_setups(bars: Sequence[DailyBar], config: SwingConfig) -> list[str]:
    return [
        _breakout(bars, config),
        _pullback(bars, config),
        _dip(bars, config),
        _range_line(bars, config),
    ]


def earnings_note(
    calendar: NyseCalendar,
    config: SwingConfig,
    market: MarketData | None,
    entry_day: date | None,
) -> str:
    """One line on the earnings window. Same dates the gate uses."""
    from swing.brain.checklist import earnings_window

    if market is not None and market.instrument_type == "ETF":
        return "Earnings: ETF. There is no company report, so this check passes."
    if not config.earnings.strict:
        return "Earnings check is off."
    if market is None or not market.events_known:
        return "Earnings: the report date is unknown. A single stock is refused until a date is known."
    if entry_day is None:
        return "Earnings: the next open is missing, so the blackout has no entry session yet."
    if not market.earnings:
        return "Earnings: the calendar is empty. No report date is in the window."
    parts: list[str] = []
    for event in market.earnings:
        start, end = earnings_window(
            calendar,
            event.report_date,
            config.earnings.blackout_before_days,
            config.earnings.blackout_after_days,
        )
        cover = "covers" if start <= entry_day <= end else "does not cover"
        parts.append(
            f"report {event.report_date.isoformat()} ({event.hour}), "
            f"blackout {start.isoformat()} through {end.isoformat()}, "
            f"{cover} the entry session"
        )
    return f"Earnings: entry session {entry_day.isoformat()}. " + "; ".join(parts) + "."


def _breakout(bars: Sequence[DailyBar], config: SwingConfig) -> str:
    rule = config.setups.bo_rvol
    need = max(rule.sma_period, rule.breakout_lookback + 1)
    if len(bars) < need:
        return (
            f"Breakout: no. Need {need} sessions for the {rule.sma_period}-day average "
            f"and the prior {rule.breakout_lookback}-session high. This series has {len(bars)}."
        )
    closes = [bar.close for bar in bars]
    average = sma(closes, rule.sma_period)
    volume_average = sma([bar.volume for bar in bars[:-1]], rule.breakout_lookback)
    prior_high = max(bar.high for bar in bars[-(rule.breakout_lookback + 1) : -1])
    close = closes[-1]
    ratio = None if volume_average is None or volume_average <= 0 else bars[-1].volume / volume_average
    above_avg = average is not None and close > average
    above_high = close > prior_high
    heavy = ratio is not None and ratio >= rule.rvol_min
    mark = "yes" if above_avg and above_high and heavy else "no"
    ratio_text = "n/a" if ratio is None else f"{ratio:.2f}"
    return (
        f"Breakout: {mark}. Close {_px(close)}. "
        f"{rule.sma_period}-day average {_px(average)} ({_side(above_avg)}). "
        f"Prior {rule.breakout_lookback}-session high {_px(prior_high)} ({_side(above_high)}). "
        f"Volume {ratio_text} times the prior {rule.breakout_lookback}-session average, "
        f"and the rule needs {rule.rvol_min:.2f}."
    )


def _pullback(bars: Sequence[DailyBar], config: SwingConfig) -> str:
    rule = config.setups.pb_ema
    need = max(rule.ema_trend, rule.ema_touch)
    if len(bars) < need:
        return (
            f"Pullback: no. Need {need} sessions for the {rule.ema_trend}-day and "
            f"{rule.ema_touch}-day smoothed lines. This series has {len(bars)}."
        )
    closes = [bar.close for bar in bars]
    trend = ema(closes, rule.ema_trend)
    touch = ema(closes, rule.ema_touch)
    close = closes[-1]
    low = bars[-1].low
    above_trend = trend is not None and close > trend
    tagged = touch is not None and low <= touch
    back_above = touch is not None and close > touch
    mark = "yes" if above_trend and tagged and back_above else "no"
    return (
        f"Pullback: {mark}. Close {_px(close)}. "
        f"{rule.ema_trend}-day smoothed line {_px(trend)} ({_side(above_trend)}). "
        f"Low {_px(low)} against the {rule.ema_touch}-day smoothed line {_px(touch)} "
        f"({'tagged' if tagged else 'did not tag'} it, "
        f"and the close {'finished above it' if back_above else 'did not finish above it'}). "
        f"A smoothed line weighs recent days more than a plain average."
    )


def _dip(bars: Sequence[DailyBar], config: SwingConfig) -> str:
    rule = config.setups.rsi2_mr
    closes = [bar.close for bar in bars]
    trend = sma(closes, rule.sma_trend) if len(bars) >= rule.sma_trend else None
    reading = rsi(closes, rule.rsi_period) if len(bars) >= rule.rsi_period + 1 else None
    if trend is None and reading is None:
        need = max(rule.sma_trend, rule.rsi_period + 1)
        return (
            f"Two-day dip: no. Need {need} sessions for the {rule.sma_trend}-day average "
            f"and RSI({rule.rsi_period}). This series has {len(bars)}."
        )
    close = closes[-1]
    above = trend is not None and close > trend
    washed = reading is not None and reading < rule.rsi_max
    mark = "yes" if above and washed else "no"
    rsi_text = "n/a" if reading is None else f"{reading:.2f}"
    if trend is None:
        average = (
            f"{rule.sma_trend}-day average n/a "
            f"(need {rule.sma_trend} sessions, have {len(bars)})"
        )
    else:
        average = f"{rule.sma_trend}-day average {_px(trend)} ({_side(above)})"
    return (
        f"Two-day dip: {mark}. RSI({rule.rsi_period}) {rsi_text}. "
        f"RSI is a 0–100 score of recent up days versus down days; "
        f"the rule needs it below {rule.rsi_max}. "
        f"Close {_px(close)} versus the {average}."
    )


def _range_line(bars: Sequence[DailyBar], config: SwingConfig) -> str:
    period = config.stops.atr_period
    reading = atr(
        [bar.high for bar in bars],
        [bar.low for bar in bars],
        [bar.close for bar in bars],
        period,
    )
    if reading is None:
        return (
            f"Average daily range: not available. ATR({period}) needs {period} sessions. "
            f"This series has {len(bars)}."
        )
    return (
        f"Average daily range: {_px(reading)}. "
        f"This is ATR({period}), the typical high-to-low distance including gaps, "
        f"smoothed over {period} sessions."
    )


def _px(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}"


def _side(above: bool) -> str:
    return "above" if above else "not above"
