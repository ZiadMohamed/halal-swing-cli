"""Text and JSON views. Compact is opt-in. The disclaimer stays on both."""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from swing.codes import DecisionKind, ReasonCode
from swing.config import SwingConfig
from swing.data.errors import fix_line, kind_of
from swing.envelope import Envelope, Plan, Reason
from swing.output.instructions import build_instructions, compact_buy, compact_sell

_DEFAULT_USER_TZ = "Africa/Cairo"
_DEFAULT_MARKET_TZ = "America/New_York"


def render_json(envelope: Envelope) -> str:
    payload = envelope.model_dump(mode="json")
    return json.dumps(payload, indent=2) + "\n"


def render_text(
    envelope: Envelope,
    *,
    user_tz: str = _DEFAULT_USER_TZ,
    market_tz: str = _DEFAULT_MARKET_TZ,
    config: SwingConfig | None = None,
) -> str:
    """Print the decision. News text is not copied onto the plan numbers."""
    lines = [
        f"{envelope.ticker}  {envelope.decision.value}",
        f"config_hash {envelope.config_hash}",
    ]
    if envelope.reasons:
        lines.append("reasons: " + ", ".join(item.code.value for item in envelope.reasons))
    if envelope.warnings:
        lines.append("warnings: " + ", ".join(item.code.value for item in envelope.warnings))
    if envelope.research.status != "ok":
        lines.append(f"research: {envelope.research.status} ({envelope.research.reason})")
    if envelope.data.status != "not_loaded":
        suspect = "suspect" if envelope.data.corp_action_suspect else "clean"
        last = envelope.data.last_session or "none"
        rebuilt = " reconstructed" if envelope.data.reconstructed else ""
        lines.append(f"data: {envelope.data.status} bars={envelope.data.bar_count} last={last} {suspect}{rebuilt}")
        lines.extend(error_lines(envelope.data.errors))
    if envelope.plan is not None:
        lines.append(_plan_line(envelope.plan))
    elif envelope.equity_usd is not None:
        lines.append(f"equity_usd {json.dumps(envelope.equity_usd)} USD")
    lines.extend(_action_lines(envelope, config))
    lines.extend(_clock_lines(envelope, user_tz=user_tz, market_tz=market_tz))
    lines.append(_stage_line(envelope))
    lines.extend(_gate_lines(envelope))
    lines.append(envelope.disclaimer)
    return "\n".join(lines) + "\n"


def error_lines(errors: list[str]) -> list[str]:
    """One line per vendor error, then the fix for its class."""
    lines: list[str] = []
    for error in errors:
        lines.append(f"data error: {error}")
        kind = kind_of(error)
        if kind is None:
            continue
        env_name = error.split(":", 1)[1] if error.startswith("missing_api_key:") else None
        lines.append(f"  fix: {fix_line(kind, env_name)}")
    return lines


def _plan_line(plan: Plan) -> str:
    setup = plan.setup if plan.setup is not None else "none"
    return (
        f"plan setup={setup} "
        f"entry={json.dumps(plan.entry)} USD "
        f"stop={json.dumps(plan.stop)} USD "
        f"target={json.dumps(plan.target)} USD "
        f"size={plan.size_shares} shares "
        f"{_equity_token(plan.equity_usd)}"
        f"next_open={plan.next_open}"
    )


def _equity_token(equity_usd: float | None) -> str:
    if equity_usd is None:
        return ""
    return f"equity={json.dumps(equity_usd)} USD "


def _action_lines(envelope: Envelope, config: SwingConfig | None) -> list[str]:
    """Buy and sell steps for ENTER_LONG. Other decisions stay quiet."""
    if envelope.decision is not DecisionKind.ENTER_LONG or envelope.plan is None:
        return []
    policy = config or SwingConfig()
    if envelope.compact:
        return [
            compact_buy(envelope.ticker, envelope.plan),
            compact_sell(envelope.plan, policy.stops.reward_r),
        ]
    built = envelope.instructions or build_instructions(
        ticker=envelope.ticker,
        plan=envelope.plan,
        config=policy,
    )
    return [built.buy, built.sell]


def _stage_line(envelope: Envelope) -> str:
    if envelope.stage == "skeleton":
        if envelope.data.status == "not_loaded":
            return "stage: skeleton — data and brain not run"
        return "stage: skeleton — brain not run"
    return f"stage: {envelope.stage}"


def _gate_lines(envelope: Envelope) -> list[str]:
    if envelope.compact:
        if not envelope.gates:
            return []
        body = " ".join(f"{gate.name}={gate.status}" for gate in envelope.gates)
        return [f"gates: {body}"]
    return [f"  {gate.name}: {gate.status}" for gate in envelope.gates]


def _clock_lines(envelope: Envelope, *, user_tz: str, market_tz: str) -> list[str]:
    stamps = _open_stamps(envelope)
    lines: list[str] = []
    for stamp in stamps:
        lines.extend(_format_stamp(stamp, user_tz=user_tz, market_tz=market_tz, compact=envelope.compact))
    return lines


def _open_stamps(envelope: Envelope) -> list[str]:
    stamps: list[str] = []
    if envelope.plan is not None and envelope.plan.next_open:
        stamps.append(envelope.plan.next_open)
    data_open = envelope.data.next_open
    if data_open and data_open not in stamps:
        stamps.append(data_open)
    return stamps


def _format_stamp(raw: str, *, user_tz: str, market_tz: str, compact: bool) -> list[str]:
    try:
        moment = _parse_instant(raw, market_tz)
        market = moment.astimezone(ZoneInfo(market_tz)).isoformat(timespec="seconds")
        user = moment.astimezone(ZoneInfo(user_tz)).isoformat(timespec="seconds")
    except (ValueError, ZoneInfoNotFoundError, OverflowError, OSError):
        return [f"next_open {raw}"]
    if compact:
        return [f"next_open {market_tz} {market} | {user_tz} {user}"]
    return [
        f"next_open {market_tz} {market}",
        f"next_open {user_tz} {user}",
    ]


_PLAIN: dict[ReasonCode, str] = {
    ReasonCode.PIPELINE_NOT_IMPLEMENTED: "checklist is not installed yet",
    ReasonCode.NO_MARKET_DATA: "no price bars are loaded",
    ReasonCode.DATA_STALE: "the vendor has no final bar for the last NYSE session yet",
    ReasonCode.CORP_ACTION_SUSPECT: "the price series looks wrong after a corporate action",
    ReasonCode.ILLIQUID: "the name is too illiquid",
    ReasonCode.EXDIV_BLOCK: "the ex-dividend yield blocks the entry",
    ReasonCode.EARNINGS_UNKNOWN: "earnings calendar unknown",
    ReasonCode.EARNINGS_BLACKOUT: "earnings blackout",
    ReasonCode.EQUITY_UNSET: "account equity is unset (pass --equity USD)",
    ReasonCode.HEAT_LIMIT: "portfolio heat would be too high",
    ReasonCode.MAX_POSITIONS: "too many positions are already open",
    ReasonCode.ADR_TOO_QUIET: "the daily range is too quiet",
    ReasonCode.NO_SETUP: "no setup matched",
    ReasonCode.INVALID_STOP: "the stop would not sit below the entry",
    ReasonCode.SIZE_BELOW_ONE_SHARE: "1% of equity does not buy one share",
    ReasonCode.NO_NEXT_OPEN: "the next NYSE open is unknown",
    ReasonCode.SETUP_SUPPRESSED: "the setup was suppressed",
    ReasonCode.BLOCK_SHORT: "shorts are not allowed",
    ReasonCode.BLOCK_MARGIN: "margin accounts are blocked",
    ReasonCode.BLOCK_DERIVATIVE: "options, CFDs, and futures are blocked",
    ReasonCode.BLOCK_SHARIAH_SCREEN: "no Shariah screen result",
    ReasonCode.BLOCK_SHARIAH_SECTOR: "sector is outside your screen",
    ReasonCode.BLOCK_SHARIAH_DATA: "Shariah data is missing",
    ReasonCode.BLOCK_SHARIAH_QUESTIONABLE: "the name is questionable on your screen",
    ReasonCode.BLOCK_SHARIAH_OVERRIDE_DENIED: "the Shariah override was denied",
}

_FINNHUB_UNKNOWN = "earnings calendar unknown (set FINNHUB_API_KEY)"


def render_simple(envelope: Envelope) -> str:
    """Short card. No gate list, no config hash, no long disclaimer.

    `--json` does not use this view. The default text view stays verbose.
    """
    plan = envelope.plan
    if envelope.decision is DecisionKind.ENTER_LONG and plan is not None:
        noun = "share" if plan.size_shares == 1 else "shares"
        lines = [
            (
                f"BUY {plan.size_shares} {noun} of {envelope.ticker} at next NYSE open "
                f"(planned entry ${plan.entry:,.2f} USD)"
            ),
            f"SELL stop ${plan.stop:,.2f} USD  OR  target ${plan.target:,.2f} USD",
            "Place manually in IBKR. Not advice.",
        ]
        return "\n".join(lines) + "\n"
    label = "NO TRADE" if envelope.decision is DecisionKind.NO_TRADE else "BLOCK"
    return f"{label} — {_plain_reason(envelope)}\n"


def _plain_reason(envelope: Envelope) -> str:
    errors = set(envelope.data.errors)
    primary = envelope.reasons[0] if envelope.reasons else None
    if primary is not None and primary.code is ReasonCode.EARNINGS_UNKNOWN:
        if "missing_api_key:FINNHUB_API_KEY" in errors:
            return _FINNHUB_UNKNOWN
        return _PLAIN[ReasonCode.EARNINGS_UNKNOWN]
    if "missing_api_key:FINNHUB_API_KEY" in errors and _calendar_unknown(primary):
        return _FINNHUB_UNKNOWN
    if primary is not None:
        mapped = _PLAIN.get(primary.code)
        if mapped is not None:
            return mapped
        return " ".join(primary.message.split())
    if "missing_api_key:FINNHUB_API_KEY" in errors:
        return _FINNHUB_UNKNOWN
    if "missing_api_key:MASSIVE_API_KEY" in errors:
        return "price bars unavailable (set MASSIVE_API_KEY)"
    return "no reason recorded"


def _calendar_unknown(primary: Reason | None) -> bool:
    if primary is None:
        return True
    if primary.code is ReasonCode.EARNINGS_BLACKOUT:
        return False
    text = primary.message.lower()
    return "earnings" in text and "unknown" in text


def _parse_instant(raw: str, market_tz: str) -> datetime:
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=ZoneInfo(market_tz))
    return moment
