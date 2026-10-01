"""Orchestrate guards, the checklist stub, and advisory research."""

from __future__ import annotations

import re
from collections.abc import Mapping

from swing.brain.gates import PIPELINE_GATES
from swing.brain.stub import StubBrain
from swing.codes import DecisionKind, ReasonCode
from swing.config import SwingConfig, load_config
from swing.disclaimer import DISCLAIMER, SHARIAH_NOTE
from swing.envelope import Envelope, GateView, Reason, ResearchHitView, ResearchView, ShariahView
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
    brain: StubBrain | None = None,
) -> Envelope:
    symbol = normalize_ticker(ticker)
    cfg = config if config is not None else load_config(env=env if env is not None else None)
    block = product_block(side="long", instrument="equity", account_mode=cfg.account.mode)
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
    checklist = (brain or StubBrain()).evaluate(symbol, cfg)
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
    )


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
) -> Envelope:
    return Envelope(
        ticker=ticker,
        decision=decision,
        reasons=list(reasons),
        warnings=list(warnings),
        confidence=None,
        side=None,
        plan=None,
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
        disclaimer=DISCLAIMER,
        config_hash=config.config_hash(),
        compact=compact,
        gates=_gates_or_pending(gates),
        stage="skeleton",
    )
