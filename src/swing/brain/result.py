"""Checklist result returned by the brain. Research is not a field."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from swing.codes import DecisionKind
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
    analysis: tuple[str, ...] = ()
