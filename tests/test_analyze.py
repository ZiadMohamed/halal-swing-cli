"""Analyze returns an envelope. News is not an input. Margin is rejected at config load."""

import json

import pytest
from pydantic import ValidationError

from swing.analyze import analyze
from swing.brain.gates import PIPELINE_GATES
from swing.brain.result import ChecklistResult
from swing.codes import DecisionKind, ReasonCode
from swing.config import SwingConfig
from swing.disclaimer import DISCLAIMER
from swing.envelope import Envelope, GateView, Plan, Reason


def _shariah() -> dict:
    return {"screened": False, "status": "user_supplied", "note": "n"}


def test_analyze_without_bars_is_no_trade():
    env = analyze("aapl", env={})
    assert env.ticker == "AAPL"
    assert env.schema_version == "2.0.0"
    assert env.decision is DecisionKind.NO_TRADE
    assert env.confidence is None
    assert env.side is None
    assert env.plan is None
    assert env.stage == "partial"
    assert [reason.code for reason in env.reasons] == [ReasonCode.NO_MARKET_DATA]
    assert DISCLAIMER in env.disclaimer
    assert len(env.config_hash) == 64
    assert env.config_hash == SwingConfig().config_hash()
    assert env.shariah.screened is False
    assert env.shariah.status == "user_supplied"
    assert [gate.name for gate in env.gates] == list(PIPELINE_GATES)
    assert env.gates[0].status == "no_trade"
    assert all(gate.status == "not_run" for gate in env.gates[1:])
    assert not hasattr(env, "research")


def test_two_runs_without_bars_produce_the_same_decision():
    first = analyze("MSFT", env={})
    second = analyze("MSFT", env={})
    assert second.decision == first.decision
    assert second.reasons == first.reasons
    assert second.plan == first.plan
    assert second.config_hash == first.config_hash


def test_margin_config_is_rejected_before_a_plan_exists():
    with pytest.raises(ValidationError):
        SwingConfig.model_validate({"account": {"mode": "margin"}})


def test_brain_enter_fields_reach_the_envelope():
    class _EnteringBrain:
        def evaluate(self, ticker: str, config: SwingConfig, *, market=None, positions=(), sector=None):
            del ticker, config, market, positions, sector
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

    env = analyze("AAPL", env={}, brain=_EnteringBrain())
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
            shariah=_shariah(),
            disclaimer=DISCLAIMER,
            config_hash="ab" * 32,
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
        shariah=_shariah(),
        disclaimer=DISCLAIMER,
        config_hash="ab" * 32,
        gates=[],
        stage="skeleton",
    )
    assert ok.confidence == "checklist_only"
    dumped = json.dumps(ok.model_dump(mode="json"))
    assert "ENTER_SHORT" not in dumped
    assert "research" not in ok.model_dump()


def test_confidence_is_absent_unless_entering():
    with pytest.raises(ValidationError):
        Envelope(
            ticker="AAPL",
            decision=DecisionKind.NO_TRADE,
            reasons=[Reason(code=ReasonCode.NO_MARKET_DATA, message="no bars")],
            warnings=[],
            confidence="checklist_only",
            side=None,
            plan=None,
            shariah=_shariah(),
            disclaimer=DISCLAIMER,
            config_hash="ab" * 32,
            gates=[],
            stage="skeleton",
        )
