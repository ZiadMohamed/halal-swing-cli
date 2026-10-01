"""Checklist stand-in until Chat 3. It never emits ENTER_LONG."""

from __future__ import annotations

from dataclasses import dataclass

from swing.brain.gates import PIPELINE_GATES
from swing.codes import DecisionKind, ReasonCode
from swing.config import SwingConfig
from swing.envelope import GateView, Reason


@dataclass(frozen=True)
class ChecklistResult:
    decision: DecisionKind
    reasons: tuple[Reason, ...]
    warnings: tuple[Reason, ...]
    confidence: str | None
    side: str | None
    plan: None
    gates: tuple[GateView, ...]


class StubBrain:
    """Ignores bars. Research is not an argument, on purpose."""

    def evaluate(self, ticker: str, config: SwingConfig) -> ChecklistResult:
        del ticker, config
        return ChecklistResult(
            decision=DecisionKind.NO_TRADE,
            reasons=(
                Reason(
                    code=ReasonCode.PIPELINE_NOT_IMPLEMENTED,
                    message=(
                        "Checklist brain is not installed yet (skeleton). "
                        "No entry, stop, target, or size was computed."
                    ),
                ),
            ),
            warnings=(),
            confidence=None,
            side=None,
            plan=None,
            gates=tuple(GateView(name=name, status="not_run") for name in PIPELINE_GATES),
        )
