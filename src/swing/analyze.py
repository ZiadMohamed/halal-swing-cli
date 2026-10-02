"""Orchestrate the checklist brain. No research client and no order path."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from datetime import date
from typing import Literal

from swing.brain.checklist import ChecklistBrain
from swing.brain.gates import PIPELINE_GATES
from swing.brain.positions import OpenPosition
from swing.brain.result import ChecklistResult
from swing.codes import DecisionKind
from swing.config import SwingConfig, load_config
from swing.data.factory import load_market_data
from swing.data.models import EarningsEvent, MarketData
from swing.disclaimer import DISCLAIMER, SHARIAH_NOTE
from swing.envelope import (
    DataView,
    DividendBrief,
    EarningsBrief,
    Envelope,
    GateView,
    Plan,
    Reason,
    ShariahView,
)
from swing.output.instructions import build_instructions

_TICKER = re.compile(r"[A-Z][A-Z0-9.\-]{0,9}")


def normalize_ticker(ticker: str) -> str:
    text = ticker.strip().upper()
    if not _TICKER.fullmatch(text):
        raise ValueError(f"Not a ticker: {ticker!r}")
    return text


def analyze(
    ticker: str,
    *,
    config: SwingConfig | None = None,
    env: Mapping[str, str] | None = None,
    brain: object | None = None,
    market: MarketData | None = None,
    fetch_market: bool = False,
    positions: tuple[OpenPosition, ...] = (),
    sector: str | None = None,
    equity_usd: float | None = None,
    earnings_date: date | None = None,
) -> Envelope:
    """Run one checklist pass.

    `equity_usd` overrides `account.equity_usd` for sizing on this call. The
    override is copied onto the config the brain reads and stamped on the
    envelope. The caller's config object, and its `config_hash`, stay as loaded.
    """
    symbol = normalize_ticker(ticker)
    cfg = config if config is not None else load_config(env=env if env is not None else None)
    run_cfg, effective_equity = _equity_for_run(cfg, equity_usd)
    if market is None and fetch_market:
        market = load_market_data(symbol, cfg, env=env, earnings_date=earnings_date)
    elif earnings_date is not None and market is not None:
        market = _with_earnings_override(market, symbol, earnings_date)
    checklist = _evaluate(brain or ChecklistBrain(), symbol, run_cfg, market, positions, sector)
    return _envelope(
        ticker=symbol,
        config=cfg,
        decision=checklist.decision,
        reasons=checklist.reasons,
        warnings=checklist.warnings,
        gates=checklist.gates,
        confidence=checklist.confidence,
        side=checklist.side,
        plan=_stamp_earnings(_stamp_plan_equity(checklist.plan, effective_equity), earnings_date),
        market=market,
        equity_usd=effective_equity,
    )


def _equity_for_run(config: SwingConfig, equity_usd: float | None) -> tuple[SwingConfig, float | None]:
    """Return the config the brain should read, and the equity to stamp.

    `None` keeps the loaded account equity. A number replaces it on a copy so
    the file hash is unchanged.
    """
    if equity_usd is None:
        return config, config.account.equity_usd
    equity = _finite_equity(equity_usd)
    account = config.account.model_copy(update={"equity_usd": equity})
    return config.model_copy(update={"account": account}), equity


def _finite_equity(equity_usd: float) -> float:
    if isinstance(equity_usd, bool) or not isinstance(equity_usd, (int, float)):
        raise ValueError("equity must be a non-negative finite number of USD. No equity figure was invented.")
    equity = float(equity_usd)
    if not math.isfinite(equity) or equity < 0:
        raise ValueError("equity must be a non-negative finite number of USD. No equity figure was invented.")
    return equity


def _with_earnings_override(market: MarketData, ticker: str, earnings_date: date) -> MarketData:
    from dataclasses import replace

    event = EarningsEvent(ticker=ticker, report_date=earnings_date, hour="unknown", source="override")
    return replace(
        market,
        earnings=(event,),
        events_known=True,
        earnings_source="override",
        earnings_override=earnings_date,
        earnings_disagree=False,
    )


def _stamp_earnings(plan: Plan | None, earnings_date: date | None) -> Plan | None:
    if plan is None or earnings_date is None:
        return plan
    return plan.model_copy(update={"earnings_date": earnings_date.isoformat()})


def _stamp_plan_equity(plan: Plan | None, equity_usd: float | None) -> Plan | None:
    if plan is None or plan.equity_usd == equity_usd:
        return plan
    return plan.model_copy(update={"equity_usd": equity_usd})


def _evaluate(
    brain: object,
    ticker: str,
    config: SwingConfig,
    market: MarketData | None,
    positions: tuple[OpenPosition, ...],
    sector: str | None,
) -> ChecklistResult:
    """Call the brain with market data. There is no research argument."""
    evaluate = brain.evaluate  # type: ignore[attr-defined]
    return evaluate(ticker, config, market=market, positions=positions, sector=sector)


def _stage(gates: list[GateView]) -> Literal["skeleton", "partial", "checklist"]:
    statuses = [gate.status for gate in gates]
    if all(status == "not_run" for status in statuses):
        return "skeleton"
    if any(status == "not_run" for status in statuses):
        return "partial"
    return "checklist"


def _gates_or_pending(gates: tuple[GateView, ...] | None) -> list[GateView]:
    if gates is not None:
        return list(gates)
    return [GateView(name=name, status="not_run") for name in PIPELINE_GATES]


def _data_view(market: MarketData | None) -> DataView:
    if market is None:
        return DataView()
    bars = market.bars
    return DataView(
        status=market.status,
        bars_provider=market.bars_provider,
        events_provider=market.events_provider,
        bar_count=0 if bars is None else len(bars.bars),
        first_session=None if bars is None or not bars.bars else bars.bars[0].session.isoformat(),
        last_session=None if bars is None or not bars.bars else bars.bars[-1].session.isoformat(),
        corp_action_suspect=bool(bars and bars.corp_action_suspect),
        corp_action_reasons=[] if bars is None else list(bars.corp_action_reasons),
        earnings=[
            EarningsBrief(report_date=item.report_date.isoformat(), hour=item.hour) for item in market.earnings
        ],
        dividends=[
            DividendBrief(ex_date=item.ex_date.isoformat(), amount=item.amount, currency=item.currency)
            for item in market.dividends
        ],
        next_open=market.next_open,
        errors=list(market.errors),
        events_known=market.events_known,
        earnings_source=market.earnings_source,
        instrument_type=market.instrument_type,
        reconstructed=bool(bars and bars.reconstructed),
        last_completed_session=(
            None if market.last_completed_session is None else market.last_completed_session.isoformat()
        ),
        earnings_override=None if market.earnings_override is None else market.earnings_override.isoformat(),
    )


def _instructions(decision: DecisionKind, ticker: str, plan: Plan | None, config: SwingConfig):
    if decision is not DecisionKind.ENTER_LONG or plan is None:
        return None
    return build_instructions(ticker=ticker, plan=plan, config=config)


def _envelope(
    *,
    ticker: str,
    config: SwingConfig,
    decision: DecisionKind,
    reasons: tuple[Reason, ...],
    warnings: tuple[Reason, ...],
    gates: tuple[GateView, ...] | None = None,
    confidence: Literal["checklist_only"] | None = None,
    side: Literal["long"] | None = None,
    plan: Plan | None = None,
    market: MarketData | None = None,
    equity_usd: float | None = None,
) -> Envelope:
    return Envelope(
        ticker=ticker,
        decision=decision,
        reasons=list(reasons),
        warnings=list(warnings),
        confidence=confidence,
        side=side,
        plan=plan,
        equity_usd=equity_usd,
        shariah=ShariahView(screened=False, provider=None, status="user_supplied", note=SHARIAH_NOTE),
        data=_data_view(market),
        instructions=_instructions(decision, ticker, plan, config),
        disclaimer=DISCLAIMER,
        config_hash=config.config_hash(),
        gates=_gates_or_pending(gates),
        stage=_stage(_gates_or_pending(gates)),
    )
