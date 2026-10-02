"""Checklist brain. Gates, indicators, the setup mutex, size, and heat.

Research is not an argument. Indicators read split-adjusted OHLC only, and a
corp-action-suspect series is refused before that. The fill timestamp is
`market.next_open`. The planned entry price is the signal close, because the
opening print has not happened yet. Stop is entry minus ATR(14) times the
configured multiple (1.5). Target is that risk times `reward_r` (2).

Share size is `floor(equity * per_trade / risk_per_share)`. A null
`account.equity_usd` is not replaced with a guess.

Liquidity has no locked dollar floor. Fewer than 20 sessions, or a
non-positive 20-session average of close times volume, is illiquid.

Ex-div is judged on the entry session only. Yield is cash amount divided by
the prior adjusted close. `exdiv.strict` blocks that session. Otherwise a
yield at or above `block_yield_gte` blocks and a smaller or unknown yield
warns. Dividend data is optional and never decides `events_known`.

Earnings blackout, when `earnings.strict`, is NYSE sessions from T minus
`blackout_before_days` through T plus `blackout_after_days`. `hour` is named
in the reason and does not move the window. An unknown calendar (`events_known`
false) does not enter while strict is on. An empty calendar enters only when
events are known. An ETF has no earnings and passes this gate with a note.

The signal bar must be the last completed NYSE session when the data layer
stamps one (`DATA_STALE` otherwise).
"""

from __future__ import annotations

import math
from datetime import date, datetime
from zoneinfo import ZoneInfo

from swing.brain.gates import PIPELINE_GATES
from swing.brain.indicators import atr
from swing.brain.positions import OpenPosition
from swing.brain.result import ChecklistResult
from swing.brain.setups import (
    SuspectSeries,
    bo_rvol_signal,
    pb_ema_signal,
    refuse_suspect,
    rsi2_signal,
    select_setup,
)
from swing.codes import DecisionKind, ReasonCode
from swing.config import SwingConfig
from swing.data.calendar import NyseCalendar
from swing.data.models import DailyBar, MarketData
from swing.envelope import GateView, Plan, Reason

_NY = ZoneInfo("America/New_York")
_LIQUIDITY_SESSIONS = 20


def earnings_window(calendar: NyseCalendar, report_date: date, before: int, after: int) -> tuple[date, date]:
    """Inclusive NYSE-session blackout around the announcement date T."""
    anchor = calendar.session_on_or_before(report_date)
    start = calendar.shift_session(anchor, -before)
    end = calendar.shift_session(anchor, after)
    return start, end


class ChecklistBrain:
    """Walk `PIPELINE_GATES` in order. One ENTER_LONG, losers suppressed."""

    def __init__(self, calendar: NyseCalendar | None = None) -> None:
        self._calendar = calendar or NyseCalendar()

    def evaluate(
        self,
        ticker: str,
        config: SwingConfig,
        market: MarketData | None = None,
        positions: tuple[OpenPosition, ...] = (),
        sector: str | None = None,
    ) -> ChecklistResult:
        del ticker
        book = tuple(positions)
        gates: dict[str, str] = {}
        warnings: list[Reason] = []

        def finish(
            decision: DecisionKind,
            reasons: tuple[Reason, ...] = (),
            *,
            plan: Plan | None = None,
        ) -> ChecklistResult:
            entering = decision is DecisionKind.ENTER_LONG
            return ChecklistResult(
                decision=decision,
                reasons=reasons,
                warnings=tuple(warnings),
                confidence="checklist_only" if entering else None,
                side="long" if entering else None,
                plan=plan,
                gates=tuple(GateView(name=name, status=gates.get(name, "not_run")) for name in PIPELINE_GATES),
            )

        def halt(gate: str, status: str, code: ReasonCode, message: str) -> ChecklistResult:
            gates[gate] = status
            return finish(DecisionKind.NO_TRADE, (Reason(code=code, message=message),))

        bars = _tradable_bars(market)
        if isinstance(bars, Reason):
            gates["data_auth"] = "no_trade"
            return finish(DecisionKind.NO_TRADE, (bars,))
        gates["data_auth"] = "pass"
        if market is not None and market.bars is not None and market.bars.reconstructed:
            warnings.append(
                Reason(
                    code=ReasonCode.WARN_BAR_RECONSTRUCTED,
                    message=(
                        f"The {bars[-1].session.isoformat()} bar was rebuilt from 1-hour bars because the "
                        "vendor's daily row was missing or not finite. Check the close in IBKR before you buy."
                    ),
                )
            )

        liquidity = _liquidity_problem(bars)
        if liquidity is not None:
            return halt("liquidity", "no_trade", ReasonCode.ILLIQUID, liquidity)
        gates["liquidity"] = "pass"

        entry_day = _entry_day(market.next_open) if market is not None else None
        exdiv = _exdiv_decision(config, market, bars, entry_day)
        if exdiv is not None and exdiv[0] == "block":
            return halt("soft_veto", "block", ReasonCode.EXDIV_BLOCK, exdiv[1])
        if exdiv is not None and exdiv[0] == "warn":
            warnings.append(Reason(code=ReasonCode.WARN_EXDIV, message=exdiv[1]))
            gates["soft_veto"] = "warn"
        else:
            gates["soft_veto"] = "pass"

        if market is not None and market.instrument_type == "ETF":
            warnings.append(
                Reason(
                    code=ReasonCode.NOTE_ETF_NO_EARNINGS,
                    message="ETF: there are no earnings reports, so the earnings gate passes.",
                )
            )
        else:
            earnings = _earnings_problem(self._calendar, config, market, entry_day)
            if earnings is not None:
                return halt("earnings", "no_trade", earnings[0], earnings[1])
        gates["earnings"] = "pass"

        gates["regime"] = "pass"

        heat = _heat_problem(config, book, sector)
        if heat is not None:
            return halt("heat", "no_trade", heat[0], heat[1])
        gates["heat"] = "pass"

        matched: set[str] = set()
        if bo_rvol_signal(bars, config):
            matched.add("BO_RVOL")
        if pb_ema_signal(bars, config):
            matched.add("PB_EMA")
        if rsi2_signal(bars, config):
            matched.add("RSI2_MR")
        winner, suppressed = select_setup(config.setups.mutex_order, matched)
        if winner is None:
            return halt(
                "setup_mutex",
                "no_trade",
                ReasonCode.NO_SETUP,
                "No setup matched. Mutex order is BO_RVOL, then PB_EMA, then RSI2_MR.",
            )
        for name in suppressed:
            warnings.append(
                Reason(
                    code=ReasonCode.SETUP_SUPPRESSED,
                    message=f"{name} matched and was suppressed. Mutex keeps {winner}.",
                )
            )
        gates["setup_mutex"] = "pass"

        sized = _size(config, bars)
        if isinstance(sized, Reason):
            return halt("rr_stop", "no_trade", sized.code, sized.message)
        entry, stop, target, shares = sized
        gates["rr_stop"] = "pass"

        if market is None or not market.next_open or entry_day is None:
            return halt(
                "next_open",
                "no_trade",
                ReasonCode.NO_NEXT_OPEN,
                "market.next_open is missing, so the next NYSE open fill is unknown.",
            )
        gates["next_open"] = "pass"
        plan = Plan(
            side="long",
            entry=entry,
            stop=stop,
            target=target,
            size_shares=shares,
            next_open=market.next_open,
            setup=winner,  # type: ignore[arg-type]
            equity_usd=config.account.equity_usd,
        )
        return finish(DecisionKind.ENTER_LONG, plan=plan)


def _tradable_bars(market: MarketData | None) -> tuple[DailyBar, ...] | Reason:
    if market is None or market.bars is None or not market.bars.bars:
        return Reason(
            code=ReasonCode.NO_MARKET_DATA,
            message="No split-adjusted bars are loaded, so the checklist did not run.",
        )
    try:
        refuse_suspect(market.bars)
    except SuspectSeries as exc:
        return Reason(code=ReasonCode.CORP_ACTION_SUSPECT, message=str(exc))
    signal = market.bars.bars[-1]
    prices = (signal.open, signal.high, signal.low, signal.close)
    if any(not math.isfinite(price) or price <= 0 for price in prices):
        return Reason(
            code=ReasonCode.NO_MARKET_DATA,
            message="The signal bar close is not a positive finite price.",
        )
    expected = market.last_completed_session
    if expected is not None and signal.session != expected:
        return Reason(
            code=ReasonCode.DATA_STALE,
            message=(
                f"The last usable bar is {signal.session.isoformat()}, but the last completed NYSE session "
                f"is {expected.isoformat()}. The vendor has not published a final bar for it yet."
            ),
        )
    return market.bars.bars


def _liquidity_problem(bars: tuple[DailyBar, ...]) -> str | None:
    if len(bars) < _LIQUIDITY_SESSIONS:
        return f"Need {_LIQUIDITY_SESSIONS} sessions to judge liquidity. This series has {len(bars)}."
    window = bars[-_LIQUIDITY_SESSIONS:]
    dollar = [bar.close * bar.volume for bar in window]
    average = sum(dollar) / _LIQUIDITY_SESSIONS
    if not math.isfinite(average) or average <= 0:
        return "20-session average dollar volume is not positive."
    return None


def _exdiv_decision(
    config: SwingConfig,
    market: MarketData | None,
    bars: tuple[DailyBar, ...],
    entry_day: date | None,
) -> tuple[str, str] | None:
    if market is None or entry_day is None:
        return None
    blocking: str | None = None
    warning: str | None = None
    for dividend in market.dividends:
        if dividend.ex_date != entry_day:
            continue
        prior = _prior_close(bars, dividend.ex_date)
        yield_ratio = None if prior is None or dividend.amount is None else dividend.amount / prior
        if config.exdiv.strict or (yield_ratio is not None and yield_ratio >= config.exdiv.block_yield_gte):
            shown = "unknown" if yield_ratio is None else f"{yield_ratio:.4f}"
            blocking = (
                f"Ex-div on the entry session {entry_day.isoformat()} blocks. "
                f"Cash yield {shown} versus block_yield_gte {config.exdiv.block_yield_gte}."
            )
            break
        shown = "unknown" if yield_ratio is None else f"{yield_ratio:.4f}"
        warning = (
            f"Ex-div on the entry session {entry_day.isoformat()} (cash yield {shown}). "
            "Ordinary ex-div warns and does not change entry, stop, target, or size."
        )
    if blocking is not None:
        return "block", blocking
    if warning is not None:
        return "warn", warning
    return None


def _prior_close(bars: tuple[DailyBar, ...], ex_date: date) -> float | None:
    earlier = [bar.close for bar in bars if bar.session < ex_date and bar.close > 0]
    if not earlier:
        return None
    return earlier[-1]


def _earnings_problem(
    calendar: NyseCalendar,
    config: SwingConfig,
    market: MarketData | None,
    entry_day: date | None,
) -> tuple[ReasonCode, str] | None:
    if not config.earnings.strict or market is None:
        return None
    if not market.events_known:
        return (
            ReasonCode.EARNINGS_UNKNOWN,
            "Earnings calendar is unknown and earnings.strict is on. Refusing ENTER_LONG. "
            "An empty list is not treated as a clear calendar.",
        )
    if entry_day is None:
        return None
    for event in market.earnings:
        start, end = earnings_window(
            calendar,
            event.report_date,
            config.earnings.blackout_before_days,
            config.earnings.blackout_after_days,
        )
        if start <= entry_day <= end:
            return (
                ReasonCode.EARNINGS_BLACKOUT,
                f"Earnings {event.report_date.isoformat()} ({event.hour}) blackout "
                f"{start.isoformat()} through {end.isoformat()} covers the entry session "
                f"{entry_day.isoformat()}.",
            )
    return None


def _heat_problem(
    config: SwingConfig,
    positions: tuple[OpenPosition, ...],
    sector: str | None,
) -> tuple[ReasonCode, str] | None:
    if any(position.risk_fraction < 0 for position in positions):
        return ReasonCode.HEAT_LIMIT, "An open position has negative risk. Heat was not computed."
    if len(positions) >= config.max_concurrent_positions:
        return (
            ReasonCode.MAX_POSITIONS,
            f"{len(positions)} positions are already open. The maximum is {config.max_concurrent_positions}.",
        )
    total = round(sum(position.risk_fraction for position in positions) + config.risk.per_trade, 10)
    if total > config.heat.total_max:
        return (
            ReasonCode.HEAT_LIMIT,
            f"Total heat would be {total:.4f}, above {config.heat.total_max:.4f}.",
        )
    if sector:
        used = round(
            sum(position.risk_fraction for position in positions if position.sector == sector) + config.risk.per_trade,
            10,
        )
        if used > config.heat.sector_max:
            return (
                ReasonCode.HEAT_LIMIT,
                f"Sector {sector} heat would be {used:.4f}, above {config.heat.sector_max:.4f}.",
            )
    return None


def _size(config: SwingConfig, bars: tuple[DailyBar, ...]) -> tuple[float, float, float, int] | Reason:
    equity = config.account.equity_usd
    if equity is None:
        return Reason(
            code=ReasonCode.EQUITY_UNSET,
            message="account.equity_usd is unset. No share size was computed and no equity figure was invented.",
        )
    entry = bars[-1].close
    highs = [bar.high for bar in bars]
    lows = [bar.low for bar in bars]
    closes = [bar.close for bar in bars]
    reading = atr(highs, lows, closes, config.stops.atr_period)
    if reading is None or reading <= 0:
        return Reason(
            code=ReasonCode.INVALID_STOP,
            message="ATR is not positive, so the stop would not sit below the entry.",
        )
    risk_per_share = config.stops.atr_multiple * reading
    stop = entry - risk_per_share
    if stop <= 0 or stop >= entry:
        return Reason(
            code=ReasonCode.INVALID_STOP,
            message="The stop is not strictly below a positive entry.",
        )
    target = entry + config.stops.reward_r * risk_per_share
    shares = math.floor((equity * config.risk.per_trade) / risk_per_share)
    if shares < 1:
        return Reason(
            code=ReasonCode.SIZE_BELOW_ONE_SHARE,
            message="1% of equity does not buy one share at this stop distance.",
        )
    return entry, stop, target, shares


def _entry_day(next_open: str | None) -> date | None:
    if not next_open:
        return None
    text = next_open.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=_NY)
    else:
        moment = moment.astimezone(_NY)
    return moment.date()
