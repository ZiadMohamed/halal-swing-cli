"""Decision envelope schema 1.1.0."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from swing.codes import DecisionKind, ReasonCode


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Reason(_Strict):
    code: ReasonCode
    message: str


class GateView(_Strict):
    name: str
    status: Literal["not_run", "pass", "warn", "block", "no_trade"]


class Plan(_Strict):
    side: Literal["long"]
    entry: float
    stop: float
    target: float
    size_shares: int = Field(ge=0)
    next_open: str


class ShariahView(_Strict):
    screened: Literal[False] = False
    provider: str | None = None
    status: Literal["user_supplied"] = "user_supplied"
    note: str


class ResearchHitView(_Strict):
    title: str
    url: str
    snippet: str


class ResearchView(_Strict):
    status: Literal["ok", "skipped", "error"]
    provider: str
    reason: str | None = None
    query: str | None = None
    hits: list[ResearchHitView] = Field(default_factory=list)
    advisory_only: Literal[True] = True
    affects_checklist_math: Literal[False] = False


class Envelope(_Strict):
    schema_version: Literal["1.1.0"] = "1.1.0"
    ticker: str
    decision: DecisionKind
    reasons: list[Reason]
    warnings: list[Reason]
    confidence: Literal["checklist_only"] | None
    side: Literal["long"] | None
    plan: Plan | None
    shariah: ShariahView
    research: ResearchView
    disclaimer: str
    config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    compact: bool
    gates: list[GateView]
    stage: Literal["skeleton"] = "skeleton"

    @model_validator(mode="after")
    def _enter_rules(self) -> Envelope:
        if self.decision is DecisionKind.ENTER_LONG:
            if self.confidence != "checklist_only":
                raise ValueError("ENTER_LONG requires confidence checklist_only")
            if self.side != "long":
                raise ValueError("ENTER_LONG is long only")
            if self.plan is None:
                raise ValueError("ENTER_LONG requires a plan")
        elif self.confidence is not None:
            raise ValueError("confidence is only stamped on ENTER_LONG")
        return self
