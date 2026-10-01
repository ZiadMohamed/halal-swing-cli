"""Skeleton analyze returns an envelope and does not let news move the checklist."""

import json

import pytest
from pydantic import ValidationError

from swing.analyze import analyze
from swing.brain.gates import PIPELINE_GATES
from swing.codes import SHARIAH_REASON_CODES, DecisionKind, ReasonCode
from swing.config import SwingConfig
from swing.disclaimer import DISCLAIMER
from swing.envelope import Envelope, Plan, Reason
from swing.research.models import ResearchHit, ResearchResult


def _note(**kwargs) -> ResearchResult:
    base = dict(
        status="ok",
        provider="fake",
        reason=None,
        query="AAPL stock news",
        hits=(ResearchHit(title="t", url="https://example.com", snippet="s"),),
        advisory_only=True,
        affects_checklist_math=False,
    )
    base.update(kwargs)
    return ResearchResult(**base)


def test_stub_analyze_envelope_without_a_context_key():
    env = analyze("aapl", env={})
    assert env.ticker == "AAPL"
    assert env.schema_version == "1.1.0"
    assert env.decision is DecisionKind.NO_TRADE
    assert env.confidence is None
    assert env.side is None
    assert env.plan is None
    assert env.stage == "skeleton"
    assert [reason.code for reason in env.reasons] == [ReasonCode.PIPELINE_NOT_IMPLEMENTED]
    assert any(warning.code is ReasonCode.WARN_RESEARCH_UNAVAILABLE for warning in env.warnings)
    assert DISCLAIMER in env.disclaimer
    assert "Not financial advice" in env.disclaimer
    assert "certif" in env.disclaimer.lower()
    assert len(env.config_hash) == 64
    assert env.config_hash == SwingConfig().config_hash()
    assert env.shariah.screened is False
    assert env.shariah.status == "user_supplied"
    assert env.research.status == "skipped"
    assert env.research.affects_checklist_math is False
    assert [gate.name for gate in env.gates] == list(PIPELINE_GATES)
    assert all(gate.status == "not_run" for gate in env.gates)
    emitted = {item.code for item in (*env.reasons, *env.warnings)}
    assert emitted.isdisjoint(SHARIAH_REASON_CODES)


def test_live_notes_do_not_change_the_checklist_decision():
    quiet = analyze("MSFT", env={})
    noisy = analyze("MSFT", env={}, research_result=_note())
    assert noisy.decision == quiet.decision
    assert noisy.reasons == quiet.reasons
    assert noisy.plan == quiet.plan
    assert noisy.config_hash == quiet.config_hash
    assert noisy.confidence == quiet.confidence
    assert noisy.research.status == "ok"
    assert noisy.research.hits[0].title == "t"
    assert all(warning.code is not ReasonCode.WARN_RESEARCH_UNAVAILABLE for warning in noisy.warnings)


def test_margin_config_blocks_before_a_plan_exists():
    cfg = SwingConfig.model_validate({"account": {"mode": "margin"}})
    env = analyze("AAPL", config=cfg, env={})
    assert env.decision is DecisionKind.BLOCK
    assert env.reasons[0].code is ReasonCode.BLOCK_MARGIN
    assert env.plan is None
    assert env.confidence is None
    assert env.research.status == "skipped"
    assert env.research.reason == "not_run_product_block"


def test_insecure_research_url_warns_and_keeps_the_checklist():
    env = analyze(
        "AAPL",
        env={"CONTEXT_DEV_API_KEY": "ctxt_secret", "CONTEXT_DEV_BASE_URL": "http://evil.example/v1"},
    )
    assert env.decision is DecisionKind.NO_TRADE
    assert env.reasons[0].code is ReasonCode.PIPELINE_NOT_IMPLEMENTED
    assert any(warning.code is ReasonCode.WARN_RESEARCH_ERROR for warning in env.warnings)
    assert env.research.reason == "insecure_base_url"
    assert env.plan is None


def test_brain_enter_fields_reach_the_envelope():
    class _EnteringBrain:
        def evaluate(self, ticker: str, config: SwingConfig):
            del ticker, config
            from swing.brain.stub import ChecklistResult
            from swing.envelope import GateView

            return ChecklistResult(
                decision=DecisionKind.ENTER_LONG,
                reasons=(),
                warnings=(),
                confidence="checklist_only",
                side="long",
                plan=Plan(
                    side="long",
                    entry=100.0,
                    stop=90.0,
                    target=120.0,
                    size_shares=4,
                    next_open="2026-10-02T13:30:00-04:00",
                ),
                gates=tuple(GateView(name=name, status="pass") for name in PIPELINE_GATES),
            )

    env = analyze("AAPL", env={}, brain=_EnteringBrain(), research_result=_note())
    assert env.decision is DecisionKind.ENTER_LONG
    assert env.confidence == "checklist_only"
    assert env.side == "long"
    assert env.plan is not None and env.plan.size_shares == 4


def test_invalid_ticker_is_rejected():
    with pytest.raises(ValueError):
        analyze("   ", env={})
    with pytest.raises(ValueError):
        analyze("not a ticker", env={})


def test_enter_long_must_stamp_checklist_only():
    plan = Plan(
        side="long",
        entry=100.0,
        stop=90.0,
        target=120.0,
        size_shares=10,
        next_open="2026-10-02T13:30:00-04:00",
    )
    with pytest.raises(ValidationError):
        Envelope(
            ticker="AAPL",
            decision=DecisionKind.ENTER_LONG,
            reasons=[],
            warnings=[],
            confidence=None,
            side="long",
            plan=plan,
            shariah={"screened": False, "status": "user_supplied", "note": "n"},
            research={
                "status": "skipped",
                "provider": "none",
                "reason": "disabled",
                "advisory_only": True,
                "affects_checklist_math": False,
            },
            disclaimer=DISCLAIMER,
            config_hash="ab" * 32,
            compact=False,
            gates=[],
            stage="skeleton",
        )
    ok = Envelope(
        ticker="AAPL",
        decision=DecisionKind.ENTER_LONG,
        reasons=[],
        warnings=[],
        confidence="checklist_only",
        side="long",
        plan=plan,
        shariah={"screened": False, "status": "user_supplied", "note": "n"},
        research={
            "status": "skipped",
            "provider": "none",
            "reason": "disabled",
            "advisory_only": True,
            "affects_checklist_math": False,
        },
        disclaimer=DISCLAIMER,
        config_hash="ab" * 32,
        compact=False,
        gates=[],
        stage="skeleton",
    )
    assert ok.confidence == "checklist_only"
    dumped = json.dumps(ok.model_dump(mode="json"))
    assert "ENTER_SHORT" not in dumped


def test_confidence_is_absent_unless_entering():
    with pytest.raises(ValidationError):
        Envelope(
            ticker="AAPL",
            decision=DecisionKind.NO_TRADE,
            reasons=[Reason(code=ReasonCode.PIPELINE_NOT_IMPLEMENTED, message="stub")],
            warnings=[],
            confidence="checklist_only",
            side=None,
            plan=None,
            shariah={"screened": False, "status": "user_supplied", "note": "n"},
            research={
                "status": "skipped",
                "provider": "none",
                "reason": "disabled",
                "advisory_only": True,
                "affects_checklist_math": False,
            },
            disclaimer=DISCLAIMER,
            config_hash="ab" * 32,
            compact=False,
            gates=[],
            stage="skeleton",
        )
