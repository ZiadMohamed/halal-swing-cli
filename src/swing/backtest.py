"""Portfolio backtest. Signals at the close, fills at the next open.

Costs are $1 plus 5 bps per side. Sale proceeds settle the next session.
Variants are the Appendix A list. This module does not search parameters.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import date

from swing.brain.portfolio import scan_allocations
from swing.brain.rules import Candidate, SignalTape, Variant, candidate_for, regime_allows
from swing.config import SwingConfig
from swing.data.calendar import NyseCalendar
from swing.data.models import DailyBar

COMMISSION = 1.0
BPS = 0.0005
START_EQUITY = 100_000.0

_ALL = ("BO_RVOL", "PB_EMA", "RSI2_MR")


def _variant(name: str, **changes: object) -> Variant:
    base = dict(
        name=name,
        triggers=_ALL,
        rank="momentum",
        seed=42,
        exit="target_2r",
        slots=4,
        max_position_frac=0.25,
        risk=0.01,
        regime=True,
        earnings="exit",
        entry_cap_atr=None,
    )
    base.update(changes)
    return Variant(**base)  # type: ignore[arg-type]


VARIANTS: dict[str, Variant] = {
    "A": _variant("A", rank="random", exit="target_2r", max_position_frac=None, regime=False, earnings="blackout"),
    "B": _variant("B", triggers=("RSI2_MR",), entry_cap_atr=0.25),
    "C": _variant("C"),
    "M": _variant("M"),
    "D2": _variant("D2", exit="trail"),
    "I": _variant("I", exit="trail", slots=5, max_position_frac=0.20),
    "J": _variant("J", exit="trail", rank="random"),
    "K": _variant("K", exit="trail", regime=False),
    "L": _variant("L", triggers=("RSI2_MR",), exit="trail"),
    "H": _variant("H", exit="trail", entry_cap_atr=0.25),
    "E": _variant("E", earnings="through"),
    "G": _variant("G", risk=0.02),
    "I_moo": _variant("I_moo", exit="trail", slots=5, max_position_frac=0.20, entry_cap_atr=None),
    "I_cap": _variant("I_cap", exit="trail", slots=5, max_position_frac=0.20, entry_cap_atr=1.0),
    "v1": _variant(
        "v1",
        exit="trail",
        slots=5,
        max_position_frac=0.20,
        entry_cap_atr=1.0,
        trend_sma=200,
        min_price=5.0,
        min_median_dollar_volume=10_000_000,
        min_sessions=260,
    ),
    "v1_random": _variant(
        "v1_random",
        rank="random",
        exit="trail",
        slots=5,
        max_position_frac=0.20,
        entry_cap_atr=1.0,
        trend_sma=200,
        min_price=5.0,
        min_median_dollar_volume=10_000_000,
        min_sessions=260,
    ),
}


@dataclass
class Trade:
    ticker: str
    entry_session: date
    exit_session: date
    entry: float
    exit: float
    shares: int
    r_multiple: float
    pct_equity: float
    reason: str


@dataclass
class Metrics:
    cagr: float
    max_dd: float
    sharpe: float
    invested: float
    trades_per_year: float
    mean_r: float
    se_r: float
    worst_pct: float
    share_loss_gt_1_5: float
    trades: int
    end_equity: float


@dataclass
class BacktestResult:
    variant: str
    metrics: Metrics
    trades: list[Trade]
    equity: list[float]
    benchmarks: dict[str, Metrics] = field(default_factory=dict)


@dataclass
class _Position:
    ticker: str
    shares: int
    entry: float
    entry_session: date
    stop: float
    risk: float
    target: float | None
    trail: float | None
    peak: float
    exit_by: date | None
    entry_equity: float


def _candidates_from_tapes(
    tapes: dict[str, SignalTape],
    session: date,
    *,
    variant: Variant,
    calendar: NyseCalendar,
    earnings: dict[str, tuple[date, ...]] | None,
    spy: tuple[DailyBar, ...] | None,
    held: set[str],
) -> list[Candidate]:
    if variant.regime and not _regime_on(spy, session):
        return []
    reports = earnings or {}
    found: list[Candidate] = []
    for ticker, tape in tapes.items():
        if ticker in held:
            continue
        item = tape.candidate(session, ticker, variant, calendar, reports.get(ticker, ()))
        if item is not None:
            found.append(item)
    return found


def scan_day(
    panels: dict[str, tuple[DailyBar, ...]],
    session: date,
    *,
    variant: Variant,
    config: SwingConfig,
    calendar: NyseCalendar,
    earnings: dict[str, tuple[date, ...]] | None = None,
    spy: tuple[DailyBar, ...] | None = None,
    held: set[str] | None = None,
) -> list[Candidate]:
    """Candidates for one session. The backtest day loop calls this and nothing else."""
    return candidates_on(
        panels,
        session,
        variant=variant,
        config=config,
        calendar=calendar,
        earnings=earnings,
        spy=spy,
        held=held,
    )


def candidates_on(
    panels: dict[str, tuple[DailyBar, ...]],
    session: date,
    *,
    variant: Variant,
    config: SwingConfig,
    calendar: NyseCalendar,
    earnings: dict[str, tuple[date, ...]] | None = None,
    spy: tuple[DailyBar, ...] | None = None,
    held: set[str] | None = None,
) -> list[Candidate]:
    """Every ticker that signals on `session`. Scan and the day loop both use this."""
    if variant.regime and not _regime_on(spy, session):
        return []
    held_now = held or set()
    found: list[Candidate] = []
    reports = earnings or {}
    for ticker, bars in panels.items():
        if ticker in held_now:
            continue
        prefix = _prefix(bars, session)
        if prefix is None:
            continue
        item = candidate_for(
            ticker,
            prefix,
            config=config,
            variant=variant,
            calendar=calendar,
            earnings=reports.get(ticker, ()),
        )
        if item is not None and item.session == session:
            found.append(item)
    return found


def run_backtest(
    panels: dict[str, tuple[DailyBar, ...]],
    *,
    variant: Variant,
    start: date,
    end: date,
    config: SwingConfig | None = None,
    calendar: NyseCalendar | None = None,
    earnings: dict[str, tuple[date, ...]] | None = None,
    spy: tuple[DailyBar, ...] | None = None,
    benchmarks: dict[str, tuple[DailyBar, ...]] | None = None,
    equity0: float = START_EQUITY,
) -> BacktestResult:
    policy = config or SwingConfig()
    clock = calendar or NyseCalendar()
    tapes = {ticker: SignalTape(bars, policy) for ticker, bars in panels.items()}
    sessions = [day for day in _sessions(clock, start, end)]
    index = {ticker: {bar.session: bar for bar in bars} for ticker, bars in panels.items()}
    cash = equity0
    unsettled: list[tuple[date, float]] = []
    positions: dict[str, _Position] = {}
    planned: list = []
    trades: list[Trade] = []
    curve: list[float] = []
    invested_days = 0
    rng = random.Random(variant.seed)
    for session in sessions:
        cash += _settle(unsettled, session)
        marked = _equity(cash, unsettled, positions, session, index)
        cash = _fill_entries(planned, session, index, positions, variant, cash, marked)
        cash, sold = _exit_positions(positions, session, index, cash, unsettled, clock)
        trades.extend(sold)
        if positions:
            invested_days += 1
        curve.append(_equity(cash, unsettled, positions, session, index))
        if session == sessions[-1]:
            break
        held = set(positions)
        todays = _candidates_from_tapes(
            tapes,
            session,
            variant=variant,
            calendar=clock,
            earnings=earnings,
            spy=spy,
            held=held,
        )
        equity = curve[-1]
        free = variant.slots - len(positions)
        planned = scan_allocations(
            todays,
            variant=variant,
            free_slots=free,
            settled_cash=cash,
            equity=equity,
            rng=rng,
        )
    years = max((end - start).days / 365.25, 1 / 365.25)
    metrics = _metrics(curve, trades, invested_days, len(sessions), years, equity0)
    benches = {
        name: _buy_hold(bars, start, end, equity0)
        for name, bars in (benchmarks or {}).items()
    }
    return BacktestResult(variant.name, metrics, trades, curve, benches)


def _fill_entries(planned, session, index, positions, variant: Variant, cash: float, marked: float) -> float:
    for allocation in planned:
        candidate = allocation.candidate
        if candidate.ticker in positions:
            continue
        bar = index.get(candidate.ticker, {}).get(session)
        if bar is None:
            continue
        if allocation.entry_cap is not None and bar.open > allocation.entry_cap:
            continue
        price = bar.open
        shares = _affordable(allocation.shares, price, cash)
        if shares < 1:
            continue
        risk = variant.initial_atr * candidate.atr
        stop = price - risk
        if stop <= 0 or risk <= 0:
            continue
        target = price + variant.target_r * risk if variant.exit == "target_2r" else None
        trail = variant.trail_atr * candidate.atr if variant.exit == "trail" else None
        positions[candidate.ticker] = _Position(
            ticker=candidate.ticker,
            shares=shares,
            entry=price,
            entry_session=session,
            stop=stop,
            risk=risk,
            target=target,
            trail=trail,
            peak=max(bar.high, price),
            exit_by=candidate.exit_by,
            entry_equity=marked,
        )
        cash -= shares * price + _cost(shares, price)
    return cash


def _affordable(shares: int, price: float, cash: float) -> int:
    if price <= 0:
        return 0
    while shares > 0 and shares * price + _cost(shares, price) > cash:
        shares -= 1
    return shares


def _exit_positions(positions, session, index, cash, unsettled, calendar: NyseCalendar):
    sold: list[Trade] = []
    for ticker in list(positions):
        position = positions[ticker]
        bar = index.get(ticker, {}).get(session)
        if bar is None:
            continue
        exit_price, reason = _exit_price(position, bar, session)
        if exit_price is None:
            if position.trail is not None:
                position.peak = max(position.peak, bar.high)
                position.stop = max(position.stop, position.peak - position.trail)
            continue
        commission = _cost(position.shares, exit_price)
        proceeds = position.shares * exit_price - commission
        try:
            settle_on = calendar.shift_session(session, 1)
        except Exception:
            settle_on = session
        unsettled.append((settle_on, proceeds))
        sold.append(
            Trade(
                ticker=ticker,
                entry_session=position.entry_session,
                exit_session=session,
                entry=position.entry,
                exit=exit_price,
                shares=position.shares,
                r_multiple=(exit_price - position.entry) / position.risk,
                pct_equity=(exit_price - position.entry) * position.shares / position.entry_equity
                if position.entry_equity
                else 0.0,
                reason=reason or "exit",
            )
        )
        del positions[ticker]
    return cash, sold


def _exit_price(position: _Position, bar: DailyBar, session: date) -> tuple[float | None, str | None]:
    if bar.open <= position.stop:
        return bar.open, "stop"
    if position.target is not None and bar.open >= position.target:
        return bar.open, "target"
    if bar.low <= position.stop:
        return position.stop, "stop"
    if position.target is not None and bar.high >= position.target:
        return position.target, "target"
    if position.exit_by is not None and session >= position.exit_by:
        return bar.close, "earnings"
    return None, None


def _equity(cash, unsettled, positions, session, index) -> float:
    marked = cash + sum(amount for _day, amount in unsettled)
    for position in positions.values():
        bar = index.get(position.ticker, {}).get(session)
        price = bar.close if bar is not None else position.entry
        marked += position.shares * price
    return marked


def _settle(unsettled: list[tuple[date, float]], session: date) -> float:
    ready = 0.0
    still: list[tuple[date, float]] = []
    for day, amount in unsettled:
        if day <= session:
            ready += amount
        else:
            still.append((day, amount))
    unsettled[:] = still
    return ready


def _cost(shares: int, price: float) -> float:
    return COMMISSION + shares * price * BPS


def _prefix(bars: tuple[DailyBar, ...], session: date) -> tuple[DailyBar, ...] | None:
    if not bars or bars[0].session > session:
        return None
    lo = 0
    hi = len(bars)
    while lo < hi:
        mid = (lo + hi) // 2
        if bars[mid].session <= session:
            lo = mid + 1
        else:
            hi = mid
    if lo == 0 or bars[lo - 1].session != session:
        return None
    return bars[:lo]


def _regime_on(spy: tuple[DailyBar, ...] | None, session: date) -> bool:
    prefix = None if spy is None else _prefix(spy, session)
    return regime_allows(prefix)


def _sessions(calendar: NyseCalendar, start: date, end: date) -> tuple[date, ...]:
    if end < start:
        return ()
    return tuple(day for day in calendar.sessions_after(start.fromordinal(start.toordinal() - 1), end) if day >= start)


def _metrics(curve, trades, invested_days, n_days, years, equity0) -> Metrics:
    end_equity = curve[-1] if curve else equity0
    cagr = (end_equity / equity0) ** (1 / years) - 1 if end_equity > 0 else -1.0
    peak = curve[0] if curve else equity0
    max_dd = 0.0
    for value in curve:
        peak = max(peak, value)
        if peak > 0:
            max_dd = min(max_dd, value / peak - 1)
    rets = [curve[i] / curve[i - 1] - 1 for i in range(1, len(curve)) if curve[i - 1] > 0]
    if len(rets) > 1:
        mean = sum(rets) / len(rets)
        var = sum((item - mean) ** 2 for item in rets) / (len(rets) - 1)
        sharpe = 0.0 if var <= 0 else mean / math.sqrt(var) * math.sqrt(252)
    else:
        sharpe = 0.0
    if trades:
        mean_r = sum(trade.r_multiple for trade in trades) / len(trades)
        var_r = sum((trade.r_multiple - mean_r) ** 2 for trade in trades) / max(len(trades) - 1, 1)
        se = math.sqrt(var_r / len(trades)) if len(trades) > 1 else 0.0
        worst = min(trade.pct_equity for trade in trades)
        losers = sum(1 for trade in trades if trade.pct_equity < -0.015)
        share = losers / len(trades)
    else:
        mean_r = se = worst = share = 0.0
    return Metrics(
        cagr=cagr,
        max_dd=max_dd,
        sharpe=sharpe,
        invested=invested_days / n_days if n_days else 0.0,
        trades_per_year=len(trades) / years,
        mean_r=mean_r,
        se_r=se,
        worst_pct=worst,
        share_loss_gt_1_5=share,
        trades=len(trades),
        end_equity=end_equity,
    )


def _buy_hold(bars: tuple[DailyBar, ...], start: date, end: date, equity0: float) -> Metrics:
    window = [bar for bar in bars if start <= bar.session <= end]
    if len(window) < 2:
        return _metrics([equity0], [], 0, 1, 1, equity0)
    first, last = window[0], window[-1]
    shares = math.floor((equity0 - COMMISSION) / (first.open * (1 + BPS)))
    if shares < 1:
        return _metrics([equity0], [], 0, len(window), max((end - start).days / 365.25, 0.01), equity0)
    cash = equity0 - shares * first.open - _cost(shares, first.open)
    curve = [cash + shares * bar.close for bar in window]
    exit_cash = cash + shares * last.close - _cost(shares, last.close)
    curve[-1] = exit_cash
    years = max((end - start).days / 365.25, 0.01)
    trade = Trade("BH", first.session, last.session, first.open, last.close, shares, 0.0, 0.0, "hold")
    return _metrics(curve, [trade], len(window), len(window), years, equity0)
