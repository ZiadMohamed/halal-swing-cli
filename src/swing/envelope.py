"""Decision envelope schema 2.0.0.

Research and the compact flag are gone. `instructions` is null unless the
decision is ENTER_LONG. Decisions are ENTER_LONG and NO_TRADE.
"""

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
    setup: Literal["BO_RVOL", "PB_EMA", "RSI2_MR"] | None = None
    equity_usd: float | None = Field(default=None, ge=0)
    earnings_date: str | None = None


class Instructions(_Strict):
    """Checklist steps for one planned cash long. Not advice. USD only."""

    currency: Literal["USD"] = "USD"
    buy: str
    sell: str


class ShariahView(_Strict):
    screened: Literal[False] = False
    provider: str | None = None
    status: Literal["user_supplied"] = "user_supplied"
    note: str


class EarningsBrief(_Strict):
    """Announcement date T. Chat 3 applies the blackout. This is not a decision."""

    report_date: str
    hour: Literal["bmo", "amc", "dmh", "unknown"]


class DividendBrief(_Strict):
    """Ex-dividend cash amount per share. The checklist compares it with price.

    `currency` is the vendor's label for that cash amount. It is not a currency
    setting. Plan prices are USD. v0 does not convert this amount.
    """

    ex_date: str
    amount: float | None = None
    currency: str = Field(
        description="Vendor label for the cash amount. Not a currency setting. Plan money is USD."
    )


class DataView(_Strict):
    """Summary of the data layer. Full bars stay on MarketData, not in this view."""

    status: Literal["ok", "partial", "error", "not_loaded"] = "not_loaded"
    bars_provider: str | None = None
    events_provider: str | None = None
    bar_count: int = 0
    first_session: str | None = None
    last_session: str | None = None
    corp_action_suspect: bool = False
    corp_action_reasons: list[str] = Field(default_factory=list)
    earnings: list[EarningsBrief] = Field(default_factory=list)
    dividends: list[DividendBrief] = Field(default_factory=list)
    next_open: str | None = None
    errors: list[str] = Field(default_factory=list)
    events_known: bool = False
    earnings_source: str | None = None
    instrument_type: Literal["EQUITY", "ETF"] | None = None
    reconstructed: bool = False
    last_completed_session: str | None = None
    earnings_override: str | None = None


class Envelope(_Strict):
    schema_version: Literal["2.0.0"] = "2.0.0"
    ticker: str
    decision: DecisionKind
    reasons: list[Reason]
    warnings: list[Reason]
    confidence: Literal["checklist_only"] | None
    side: Literal["long"] | None
    plan: Plan | None
    instructions: Instructions | None = None
    equity_usd: float | None = Field(default=None, ge=0)
    shariah: ShariahView
    data: DataView = Field(default_factory=DataView)
    disclaimer: str
    config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    gates: list[GateView]
    stage: Literal["skeleton", "partial", "checklist"] = "skeleton"
    analysis: list[str] = Field(default_factory=list)

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
        if self.decision is not DecisionKind.ENTER_LONG and self.instructions is not None:
            raise ValueError("instructions are only stamped on ENTER_LONG")
        return self
