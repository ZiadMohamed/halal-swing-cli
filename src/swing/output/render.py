"""Text and JSON views.

The default text is the action card: decision, plan, reasons, config hash,
clocks, and the disclaimer. `--explain` adds every gate and the longer
buy/sell numbers. `--json` is the envelope.
"""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from swing.codes import DecisionKind
from swing.config import SwingConfig
from swing.data.errors import fix_line, kind_of
from swing.envelope import Envelope, Plan
from swing.output.instructions import build_instructions, compact_buy, compact_sell

_DEFAULT_USER_TZ = "Africa/Cairo"
_DEFAULT_MARKET_TZ = "America/New_York"


def render_json(envelope: Envelope) -> str:
    payload = envelope.model_dump(mode="json")
    return json.dumps(payload, indent=2) + "\n"


def render_text(
    envelope: Envelope,
    *,
    explain: bool = False,
    user_tz: str = _DEFAULT_USER_TZ,
    market_tz: str = _DEFAULT_MARKET_TZ,
    config: SwingConfig | None = None,
) -> str:
    """Print the action card. `explain` adds gates, stage, and the longer steps."""
    lines = [
        f"{envelope.ticker}  {envelope.decision.value}",
        f"config_hash {envelope.config_hash}",
    ]
    if envelope.reasons:
        lines.append("reasons: " + ", ".join(item.code.value for item in envelope.reasons))
    if envelope.warnings:
        lines.append("warnings: " + ", ".join(item.code.value for item in envelope.warnings))
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
    lines.extend(_action_lines(envelope, config, explain=explain))
    lines.extend(_clock_lines(envelope, user_tz=user_tz, market_tz=market_tz))
    if explain:
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


def _action_lines(envelope: Envelope, config: SwingConfig | None, *, explain: bool) -> list[str]:
    """Buy and sell steps for ENTER_LONG. Other decisions stay quiet."""
    if envelope.decision is not DecisionKind.ENTER_LONG or envelope.plan is None:
        return []
    policy = config or SwingConfig()
    if not explain:
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
    return [f"  {gate.name}: {gate.status}" for gate in envelope.gates]


def _clock_lines(envelope: Envelope, *, user_tz: str, market_tz: str) -> list[str]:
    stamps = _open_stamps(envelope)
    lines: list[str] = []
    for stamp in stamps:
        lines.extend(_format_stamp(stamp, user_tz=user_tz, market_tz=market_tz))
    return lines


def _open_stamps(envelope: Envelope) -> list[str]:
    stamps: list[str] = []
    if envelope.plan is not None and envelope.plan.next_open:
        stamps.append(envelope.plan.next_open)
    data_open = envelope.data.next_open
    if data_open and data_open not in stamps:
        stamps.append(data_open)
    return stamps


def _format_stamp(raw: str, *, user_tz: str, market_tz: str) -> list[str]:
    try:
        moment = _parse_instant(raw, market_tz)
        market = moment.astimezone(ZoneInfo(market_tz)).isoformat(timespec="seconds")
        user = moment.astimezone(ZoneInfo(user_tz)).isoformat(timespec="seconds")
    except (ValueError, ZoneInfoNotFoundError, OverflowError, OSError):
        return [f"next_open {raw}"]
    return [
        f"next_open {market_tz} {market}",
        f"next_open {user_tz} {user}",
    ]


def _parse_instant(raw: str, market_tz: str) -> datetime:
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=ZoneInfo(market_tz))
    return moment
