"""Rank candidates and fund free slots. Scan and the backtest both call this."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from swing.brain.rules import Candidate, Variant


@dataclass(frozen=True)
class Allocation:
    candidate: Candidate
    shares: int
    entry_cap: float | None


def rank_candidates(candidates: list[Candidate], variant: Variant, rng: random.Random) -> list[Candidate]:
    if variant.rank == "random":
        ordered = list(candidates)
        rng.shuffle(ordered)
        return ordered
    return sorted(candidates, key=lambda item: item.momentum if item.momentum is not None else float("-inf"), reverse=True)


def allocate_slots(
    ranked: list[Candidate],
    *,
    variant: Variant,
    free_slots: int,
    settled_cash: float,
    equity: float,
) -> list[Allocation]:
    """Fill from the top until slots or settled cash run out. Never spends unsettled cash."""
    chosen: list[Allocation] = []
    cash = settled_cash
    for candidate in ranked:
        if len(chosen) >= free_slots or cash <= 0 or equity <= 0:
            break
        if candidate.momentum is None and variant.rank == "momentum":
            continue
        shares = _shares(candidate, variant, cash, equity)
        if shares < 1:
            continue
        cap = None if variant.entry_cap_atr is None else candidate.close + variant.entry_cap_atr * candidate.atr
        price = cap if cap is not None else candidate.close
        cost = shares * price
        if cost > cash:
            shares = math.floor(cash / price) if price > 0 else 0
        if shares < 1:
            continue
        chosen.append(Allocation(candidate, shares, cap))
        cash -= shares * price
    return chosen


def scan_allocations(
    candidates: list[Candidate],
    *,
    variant: Variant,
    free_slots: int,
    settled_cash: float,
    equity: float,
    rng: random.Random,
) -> list[Allocation]:
    return allocate_slots(
        rank_candidates(candidates, variant, rng),
        variant=variant,
        free_slots=free_slots,
        settled_cash=settled_cash,
        equity=equity,
    )


def _shares(candidate: Candidate, variant: Variant, cash: float, equity: float) -> int:
    risk_per_share = variant.initial_atr * candidate.atr
    if risk_per_share <= 0 or candidate.close <= 0:
        return 0
    risk_shares = math.floor(equity * variant.risk / risk_per_share)
    capped = risk_shares
    price = candidate.close
    if variant.entry_cap_atr is not None:
        price = candidate.close + variant.entry_cap_atr * candidate.atr
    if variant.max_position_frac is not None and price > 0:
        capped = min(capped, math.floor(variant.max_position_frac * equity / price))
    if price > 0:
        capped = min(capped, math.floor(cash / price))
    return max(capped, 0)
