"""Shared checklist result, plus a no-op brain that never emits ENTER_LONG.

`analyze` uses `ChecklistBrain`. `StubBrain` remains so a caller can force the
old all-gates-not-run result. It does not read `market`.
"""

from __future__ import annotations

from dataclasses import dataclass

from typing import Literal

from swing.brain.gates import PIPELINE_GATES
from swing.codes import DecisionKind, ReasonCode
from swing.config import SwingConfig
from swing.data.models import MarketData
from swing.envelope import GateView, Plan, Reason


@dataclass(frozen=True)
class ChecklistResult:
    decision: DecisionKind
    reasons: tuple[Reason, ...]
    warnings: tuple[Reason, ...]
    confidence: Literal["checklist_only"] | None
    side: Literal["long"] | None
    plan: Plan | None
    gates: tuple[GateView, ...]


class StubBrain:
    """Ignores bars. Research is not an argument, on purpose.

    `market` is accepted so Chat 3 can keep the same call. The stub does not
    read it and does not emit ENTER_LONG.
    """

    def evaluate(self, ticker: str, config: SwingConfig, market: MarketData | None = None) -> ChecklistResult:
        del ticker, config, market
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
