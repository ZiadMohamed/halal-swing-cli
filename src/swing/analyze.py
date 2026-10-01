"""Orchestrate guards, the checklist brain, and advisory research."""

from __future__ import annotations

import inspect
import re
from collections.abc import Mapping
from typing import Literal

from swing.brain.checklist import ChecklistBrain
from swing.brain.gates import PIPELINE_GATES
from swing.brain.positions import OpenPosition
from swing.brain.stub import ChecklistResult
from swing.codes import DecisionKind, ReasonCode
from swing.config import SwingConfig, load_config
from swing.data.factory import load_market_data
from swing.data.models import BarSeries, MarketData
from swing.disclaimer import DISCLAIMER, SHARIAH_NOTE
from swing.envelope import (
    DataView,
    DividendBrief,
    EarningsBrief,
    Envelope,
    GateView,
    Plan,
    Reason,
    ResearchHitView,
    ResearchView,
    ShariahView,
)
from swing.guards import product_block
from swing.research.factory import build_live_research
from swing.research.models import ResearchResult

_TICKER = re.compile(r"[A-Z][A-Z0-9.\-]{0,9}")

_RESEARCH_SKIP_MSG = (
    "CONTEXT_DEV_API_KEY is not set. Live news enrichment was skipped. "
    "Checklist math does not use this enrichment."
)
_RESEARCH_ERROR_MSG = "Live research failed. Checklist numbers were not changed."


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
    research_result: ResearchResult | None = None,
    compact: bool = False,
    brain: object | None = None,
    market: MarketData | None = None,
    fetch_market: bool = False,
    spy_bars: BarSeries | None = None,
    positions: tuple[OpenPosition, ...] = (),
    sector: str | None = None,
) -> Envelope:
    symbol = normalize_ticker(ticker)
    cfg = config if config is not None else load_config(env=env if env is not None else None)
    block = product_block(
        side="long",
        instrument="equity",
        account_mode=cfg.account.mode,
        longs_only=cfg.account.longs_only,
    )
    if block is not None:
        return _envelope(
            ticker=symbol,
            config=cfg,
            compact=compact,
            decision=DecisionKind.BLOCK,
            reasons=(
                Reason(
                    code=block,
                    message="Cash long equity only. This intent is outside the product.",
                ),
            ),
            warnings=(),
            research=_skipped("not_run_product_block"),
        )
    if market is None and fetch_market:
        market = load_market_data(symbol, cfg, env=env)
    if spy_bars is None and fetch_market and market is not None and market.bars is not None:
        if not market.bars.corp_action_suspect:
            spy_market = load_market_data(
                "SPY",
                cfg,
                env=env,
                lookback_sessions=cfg.spy_r2.lookback_days,
            )
            if spy_market is not None and spy_market.bars is not None and not spy_market.bars.corp_action_suspect:
                spy_bars = spy_market.bars
    checklist = _evaluate(brain or ChecklistBrain(), symbol, cfg, market, spy_bars, positions, sector)
    if research_result is None:
        research_result = build_live_research(cfg, env=env).enrich(symbol)
    warnings = list(checklist.warnings)
    warnings.extend(_research_warnings(research_result))
    return _envelope(
        ticker=symbol,
        config=cfg,
        compact=compact,
        decision=checklist.decision,
        reasons=checklist.reasons,
        warnings=tuple(warnings),
        research=research_result,
        gates=checklist.gates,
        confidence=checklist.confidence,
        side=checklist.side,
        plan=checklist.plan,
        market=market,
    )


def _evaluate(
    brain: object,
    ticker: str,
    config: SwingConfig,
    market: MarketData | None,
    spy_bars: BarSeries | None,
    positions: tuple[OpenPosition, ...],
    sector: str | None,
) -> ChecklistResult:
    """Pass bars only when the brain accepts them. Never pass research."""
    evaluate = brain.evaluate  # type: ignore[attr-defined]
    parameters = inspect.signature(evaluate).parameters
    kwargs: dict[str, object] = {}
    if "market" in parameters:
        kwargs["market"] = market
    if "spy_bars" in parameters:
        kwargs["spy_bars"] = spy_bars
    if "positions" in parameters:
        kwargs["positions"] = positions
    if "sector" in parameters:
        kwargs["sector"] = sector
    return evaluate(ticker, config, **kwargs)


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


def _research_warnings(result: ResearchResult) -> tuple[Reason, ...]:
    if result.status == "skipped" and result.reason == "missing_api_key":
        return (Reason(code=ReasonCode.WARN_RESEARCH_UNAVAILABLE, message=_RESEARCH_SKIP_MSG),)
    if result.status == "error":
        return (Reason(code=ReasonCode.WARN_RESEARCH_ERROR, message=_RESEARCH_ERROR_MSG),)
    return ()


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
    )


def _skipped(reason: str) -> ResearchResult:
    return ResearchResult(status="skipped", provider="none", reason=reason, query=None, hits=())


def _envelope(
    *,
    ticker: str,
    config: SwingConfig,
    compact: bool,
    decision: DecisionKind,
    reasons: tuple[Reason, ...],
    warnings: tuple[Reason, ...],
    research: ResearchResult,
    gates: tuple[GateView, ...] | None = None,
    confidence: Literal["checklist_only"] | None = None,
    side: Literal["long"] | None = None,
    plan: Plan | None = None,
    market: MarketData | None = None,
) -> Envelope:
    return Envelope(
        ticker=ticker,
        decision=decision,
        reasons=list(reasons),
        warnings=list(warnings),
        confidence=confidence,
        side=side,
        plan=plan,
        shariah=ShariahView(screened=False, provider=None, status="user_supplied", note=SHARIAH_NOTE),
        research=ResearchView(
            status=research.status,
            provider=research.provider,
            reason=research.reason,
            query=research.query,
            hits=[ResearchHitView(title=hit.title, url=hit.url, snippet=hit.snippet) for hit in research.hits],
            advisory_only=True,
            affects_checklist_math=False,
        ),
        data=_data_view(market),
        disclaimer=DISCLAIMER,
        config_hash=config.config_hash(),
        compact=compact,
        gates=_gates_or_pending(gates),
        stage=_stage(_gates_or_pending(gates)),
    )
