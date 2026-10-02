"""Append-only fills and plans.

`book.jsonl` is buys and sells. `plans.jsonl` is decisions, deduped on
ticker, signal session, and config hash. Neither file is rewritten.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from swing.home import swing_home

_SELL_REASONS = frozenset({"stop", "trail", "earnings", "manual"})


@dataclass(frozen=True)
class Buy:
    ticker: str
    shares: int
    price: float
    day: date
    stop: float | None
    trail_amount: float | None
    exit_by: str | None
    plan_id: str | None
    config_hash: str | None
    line: int


@dataclass(frozen=True)
class Sell:
    ticker: str
    shares: int
    price: float
    day: date
    reason: str
    line: int


@dataclass(frozen=True)
class OpenLot:
    ticker: str
    shares: int
    price: float
    day: date
    stop: float | None
    trail_amount: float | None
    exit_by: str | None
    plan_id: str | None
    config_hash: str | None


@dataclass(frozen=True)
class PlanRecord:
    ticker: str
    signal_session: str
    config_hash: str
    payload: dict


def book_path(home: Path | None = None) -> Path:
    root = swing_home() if home is None else home
    return root / "book.jsonl"


def plans_path(home: Path | None = None) -> Path:
    root = swing_home() if home is None else home
    return root / "plans.jsonl"


def load_book(path: Path) -> tuple[list[Buy | Sell], list[OpenLot]]:
    """Read fills. A bad line raises ValueError naming that line. The file is not changed."""
    if not path.is_file():
        return [], []
    events: list[Buy | Sell] = []
    remaining: dict[str, list[OpenLot]] = {}
    for index, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        events.append(_event(index, raw, remaining))
    lots = [lot for group in remaining.values() for lot in group if lot.shares > 0]
    return events, lots


def append_buy(
    path: Path,
    *,
    ticker: str,
    shares: int,
    price: float,
    day: date,
    stop: float | None = None,
    trail_amount: float | None = None,
    exit_by: str | None = None,
    plan_id: str | None = None,
    config_hash: str | None = None,
) -> None:
    if shares < 1 or price <= 0:
        raise ValueError("buy needs a positive share count and price")
    _append(
        path,
        {
            "schema": "2",
            "type": "buy",
            "ticker": ticker.strip().upper(),
            "shares": shares,
            "price": price,
            "date": day.isoformat(),
            "stop": stop,
            "trail_amount": trail_amount,
            "exit_by": exit_by,
            "plan_id": plan_id,
            "config_hash": config_hash,
        },
    )


def append_sell(
    path: Path,
    *,
    ticker: str,
    shares: int,
    price: float,
    day: date,
    reason: str = "manual",
) -> None:
    if reason not in _SELL_REASONS:
        raise ValueError("sell reason must be stop, trail, earnings, or manual")
    symbol = ticker.strip().upper()
    _events, lots = load_book(path)
    open_shares = sum(lot.shares for lot in lots if lot.ticker == symbol)
    if shares < 1 or shares > open_shares:
        raise ValueError(f"{symbol} has {open_shares} open shares")
    if price <= 0:
        raise ValueError("sell needs a positive price")
    _append(
        path,
        {
            "schema": "2",
            "type": "sell",
            "ticker": symbol,
            "shares": shares,
            "price": price,
            "date": day.isoformat(),
            "reason": reason,
        },
    )


def available_cash(equity: float, lots: list[OpenLot], events: list[Buy | Sell], today: date) -> float:
    """Settled cash: equity minus open cost basis minus same-day sale proceeds."""
    basis = sum(lot.shares * lot.price for lot in lots)
    unsettled = sum(event.shares * event.price for event in events if isinstance(event, Sell) and event.day == today)
    return equity - basis - unsettled


def open_tickers(lots: list[OpenLot]) -> set[str]:
    return {lot.ticker for lot in lots if lot.shares > 0}


def append_plan(path: Path, record: dict) -> bool:
    """Append one plan unless ticker + signal session + config hash is already there.

    Returns False when the line is a duplicate. The file is only opened for append.
    """
    ticker = str(record["ticker"]).upper()
    session = str(record["signal_session"])
    digest = str(record["config_hash"])
    if path.is_file():
        for index, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not raw.strip():
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"plans line {index} is not JSON") from exc
            if (
                isinstance(payload, dict)
                and payload.get("ticker") == ticker
                and payload.get("signal_session") == session
                and payload.get("config_hash") == digest
            ):
                return False
    stored = dict(record)
    stored["ticker"] = ticker
    stored["schema"] = "2"
    _append(path, stored)
    return True


def load_plans(path: Path) -> list[PlanRecord]:
    if not path.is_file():
        return []
    found: list[PlanRecord] = []
    for index, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"plans line {index} is not JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"plans line {index} is not an object")
        ticker = payload.get("ticker")
        session = payload.get("signal_session")
        digest = payload.get("config_hash")
        if not isinstance(ticker, str) or not isinstance(session, str) or not isinstance(digest, str):
            raise ValueError(f"plans line {index} is missing ticker, signal_session, or config_hash")
        found.append(PlanRecord(ticker, session, digest, payload))
    return found


def import_v0_journal(journal: Path, plans: Path, archive: Path) -> int:
    """Copy a v0 journal onto plans. The journal is copied to `archive` and left in place."""
    if not journal.is_file():
        return 0
    if not archive.exists():
        archive.write_bytes(journal.read_bytes())
    added = 0
    for index, raw in enumerate(journal.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"journal line {index} is not JSON") from exc
        if not isinstance(payload, dict) or payload.get("decision") != "ENTER_LONG":
            continue
        ticker = payload.get("ticker")
        digest = payload.get("config_hash") or "v0"
        session = str(payload.get("next_open") or payload.get("signal_session") or "")[:10]
        if not isinstance(ticker, str) or not session:
            raise ValueError(f"journal line {index} cannot be imported as a plan")
        record = {
            "ticker": ticker,
            "signal_session": session,
            "config_hash": digest,
            "source": "journal.v0",
            "entry": payload.get("entry"),
            "stop": payload.get("stop"),
            "target": payload.get("target"),
            "size_shares": payload.get("size_shares"),
        }
        if append_plan(plans, record):
            added += 1
    return added


def closed_trades(events: list[Buy | Sell]) -> list[dict]:
    """FIFO match of sells to buys. R uses the buy stop distance when the stop is present."""
    lots: dict[str, list[dict]] = {}
    closed: list[dict] = []
    for event in events:
        if isinstance(event, Buy):
            lots.setdefault(event.ticker, []).append(
                {
                    "shares": event.shares,
                    "price": event.price,
                    "day": event.day,
                    "stop": event.stop,
                }
            )
            continue
        left = event.shares
        queue = lots.get(event.ticker, [])
        while left > 0 and queue:
            lot = queue[0]
            take = min(left, lot["shares"])
            risk = None if lot["stop"] is None else lot["price"] - lot["stop"]
            r_multiple = None if risk is None or risk <= 0 else (event.price - lot["price"]) / risk
            closed.append(
                {
                    "ticker": event.ticker,
                    "shares": take,
                    "entry": lot["price"],
                    "exit": event.price,
                    "entry_day": lot["day"],
                    "exit_day": event.day,
                    "r": r_multiple,
                    "hold_days": (event.day - lot["day"]).days,
                    "reason": event.reason,
                }
            )
            lot["shares"] -= take
            left -= take
            if lot["shares"] == 0:
                queue.pop(0)
    return closed


def review_summary(trades: list[dict]) -> dict:
    scored = [trade for trade in trades if trade["r"] is not None]
    count = len(scored)
    if count == 0:
        return {"n": 0, "mean_r": None, "se": None, "label": "unproven", "win_rate": None, "avg_hold": None}
    mean = sum(trade["r"] for trade in scored) / count
    var = sum((trade["r"] - mean) ** 2 for trade in scored) / max(count - 1, 1)
    se = (var / count) ** 0.5 if count > 1 else 0.0
    wins = sum(1 for trade in scored if trade["r"] > 0)
    hold = sum(trade["hold_days"] for trade in scored) / count
    proven = count >= 100 and mean - 2 * se > 0
    return {
        "n": count,
        "mean_r": mean,
        "se": se,
        "label": "proven" if proven else "unproven",
        "win_rate": wins / count,
        "avg_hold": hold,
    }


def _append(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _event(index: int, raw: str, remaining: dict[str, list[OpenLot]]) -> Buy | Sell:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"book line {index} is not JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"book line {index} is not an object")
    kind = payload.get("type")
    ticker = payload.get("ticker")
    if not isinstance(ticker, str) or not ticker.strip():
        raise ValueError(f"book line {index} is missing ticker")
    symbol = ticker.strip().upper()
    shares = payload.get("shares")
    price = payload.get("price")
    if isinstance(shares, bool) or not isinstance(shares, int) or shares < 1:
        raise ValueError(f"book line {index} shares must be a positive integer")
    if isinstance(price, bool) or not isinstance(price, (int, float)) or float(price) <= 0:
        raise ValueError(f"book line {index} price must be positive")
    day = _day(payload.get("date"), index)
    if kind == "buy":
        lot = OpenLot(
            symbol,
            shares,
            float(price),
            day,
            _optional_float(payload.get("stop")),
            _optional_float(payload.get("trail_amount")),
            payload.get("exit_by") if isinstance(payload.get("exit_by"), str) else None,
            payload.get("plan_id") if isinstance(payload.get("plan_id"), str) else None,
            payload.get("config_hash") if isinstance(payload.get("config_hash"), str) else None,
        )
        remaining.setdefault(symbol, []).append(lot)
        return Buy(
            symbol,
            shares,
            float(price),
            day,
            lot.stop,
            lot.trail_amount,
            lot.exit_by,
            lot.plan_id,
            lot.config_hash,
            index,
        )
    if kind == "sell":
        reason = payload.get("reason")
        if reason not in _SELL_REASONS:
            raise ValueError(f"book line {index} reason must be stop, trail, earnings, or manual")
        left = shares
        queue = remaining.get(symbol, [])
        for lot_index, lot in enumerate(queue):
            if left == 0:
                break
            take = min(left, lot.shares)
            queue[lot_index] = OpenLot(
                lot.ticker,
                lot.shares - take,
                lot.price,
                lot.day,
                lot.stop,
                lot.trail_amount,
                lot.exit_by,
                lot.plan_id,
                lot.config_hash,
            )
            left -= take
        if left:
            raise ValueError(f"book line {index} sells more {symbol} than the book has open")
        remaining[symbol] = [lot for lot in queue if lot.shares > 0]
        return Sell(symbol, shares, float(price), day, reason, index)
    raise ValueError(f"book line {index} type must be buy or sell")


def _day(value: object, index: int) -> date:
    if not isinstance(value, str):
        raise ValueError(f"book line {index} date must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise ValueError(f"book line {index} date must be YYYY-MM-DD") from exc


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def block_if_open(ticker: str, lots: list[OpenLot]) -> bool:
    """True when a new plan must not be written for this ticker."""
    return ticker.strip().upper() in open_tickers(lots)


def score_plan(plan: dict, bars: tuple) -> float | None:
    """Replay one plan from the next open. R is (exit - fill) / (fill - stop)."""
    stop = plan.get("stop")
    if not isinstance(stop, (int, float)) or isinstance(stop, bool):
        return None
    session = str(plan.get("signal_session") or "")[:10]
    after = [bar for bar in bars if bar.session.isoformat() > session]
    if not after:
        return None
    fill = after[0].open
    risk = fill - float(stop)
    if risk <= 0:
        return None
    target = plan.get("target")
    trail = plan.get("trail_amount")
    exit_by = str(plan.get("exit_by") or "")[:10]
    active = fill - risk
    peak = after[0].high
    for bar in after:
        if bar.open <= active:
            return (bar.open - fill) / risk
        if isinstance(target, (int, float)) and not isinstance(target, bool) and bar.high >= float(target):
            return (float(target) - fill) / risk
        if exit_by and bar.session.isoformat() >= exit_by:
            return (bar.close - fill) / risk
        if isinstance(trail, (int, float)) and not isinstance(trail, bool):
            peak = max(peak, bar.high)
            active = max(active, peak - float(trail))
        if bar.low <= active:
            return (active - fill) / risk
    return None


def parse_cli_date(value: str | None) -> date:
    if value is None:
        return datetime.now().date()
    return date.fromisoformat(value)
