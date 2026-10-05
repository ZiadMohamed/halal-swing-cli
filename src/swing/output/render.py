"""Text and JSON views.

The default text is three short sections: verdict, prices, and the readings.
`--explain` adds the gates and the longer buy and sell sentences.
`--verbose` adds the config hash and the product note.
`--json` is the envelope, including both of those fields.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from swing.codes import DecisionKind, ReasonCode
from swing.config import SwingConfig
from swing.data.errors import fix_line, kind_of
from swing.envelope import Envelope
from swing.output.instructions import build_instructions

_DEFAULT_USER_TZ = "Africa/Cairo"
_DEFAULT_MARKET_TZ = "America/New_York"
_CENTS = Decimal("0.01")

_BUY_REASON = {
    "BO_RVOL": "Volume breakout matched.",
    "PB_EMA": "Pullback to the smoothed line matched.",
    "RSI2_MR": "Two-day dip above the long average matched.",
}


def render_json(envelope: Envelope) -> str:
    payload = envelope.model_dump(mode="json")
    return json.dumps(payload, indent=2) + "\n"


def render_text(
    envelope: Envelope,
    *,
    explain: bool = False,
    verbose: bool = False,
    user_tz: str = _DEFAULT_USER_TZ,
    market_tz: str = _DEFAULT_MARKET_TZ,
    config: SwingConfig | None = None,
) -> str:
    """Print the short card. `explain` adds gates. `verbose` adds the hash and the note."""
    policy = config or SwingConfig()
    lines = [
        f"{envelope.ticker}  {_verdict_word(envelope)}",
        _main_reason(envelope, policy),
        "",
        "Prices",
        *_price_lines(envelope, policy),
        "",
        "Technical",
        *[f"- {line}" for line in _technical_lines(envelope)],
    ]
    lines.extend(_user_clock_lines(envelope, user_tz=user_tz, market_tz=market_tz))
    if explain:
        lines.extend(_market_clock_lines(envelope, user_tz=user_tz, market_tz=market_tz))
        lines.append(_stage_line(envelope))
        lines.extend(_gate_lines(envelope))
        lines.extend(_long_actions(envelope, policy))
    if explain or verbose:
        lines.append(f"config_hash {envelope.config_hash}")
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


def _verdict_word(envelope: Envelope) -> str:
    if envelope.decision is DecisionKind.ENTER_LONG:
        return "BUY"
    return "NO TRADE"


def _main_reason(envelope: Envelope, config: SwingConfig) -> str:
    if envelope.decision is DecisionKind.ENTER_LONG and envelope.plan is not None and envelope.plan.setup:
        return _buy_reason(envelope.plan.setup, config)
    if envelope.reasons:
        if envelope.reasons[0].code is ReasonCode.NO_SETUP:
            return "None of the three setups matched."
        return envelope.reasons[0].message
    return "No trade."


def _buy_reason(setup: str, config: SwingConfig) -> str:
    if setup == "BO_RVOL":
        rule = config.setups.bo_rvol
        return (
            f"Volume breakout matched. The close is above the {rule.sma_period}-day average "
            f"and the prior {rule.breakout_lookback}-session high, "
            f"and volume is at least {_plain(rule.rvol_min)} times the recent average."
        )
    if setup == "PB_EMA":
        rule = config.setups.pb_ema
        return (
            f"Pullback matched. The low tagged the {rule.ema_touch}-day smoothed line "
            f"and the close finished back above it, while the close is still above "
            f"the {rule.ema_trend}-day smoothed line."
        )
    if setup == "RSI2_MR":
        rule = config.setups.rsi2_mr
        return (
            f"Two-day dip matched. The close is above the {rule.sma_trend}-day average "
            f"and RSI({rule.rsi_period}) is below {rule.rsi_max}."
        )
    return _BUY_REASON.get(setup, "A setup matched.")


def _price_lines(envelope: Envelope, config: SwingConfig) -> list[str]:
    plan = envelope.plan
    if plan is None:
        if envelope.reasons and envelope.reasons[0].code is ReasonCode.EQUITY_UNSET:
            return ["No buy price, stop, profit target, or share count. The sleeve size is unset."]
        return ["No buy price, stop, profit target, or share count."]
    distance = plan.entry - plan.stop
    risk = plan.size_shares * distance
    cost = plan.size_shares * plan.entry
    equity = plan.equity_usd if plan.equity_usd is not None else envelope.equity_usd
    sleeve = "the sleeve" if equity is None else f"{_cents(equity)} USD"
    return [
        (
            f"Buy {_cents(plan.entry)} USD. Yesterday's close. "
            "Type it in Interactive Brokers for the next open. This program does not send the order."
        ),
        (
            f"Stop {_cents(plan.stop)} USD. "
            f"{_plain(config.stops.atr_multiple)} times the {config.stops.atr_period}-day "
            "average daily range below that close."
        ),
        (
            f"Profit {_cents(plan.target)} USD. "
            f"{_reward(config.stops.reward_r)} that stop distance above the close."
        ),
        (
            f"{plan.size_shares} shares. Dollars at risk {_cents(risk)} USD. "
            f"Total cost {_cents(cost)} USD."
        ),
        (
            f"The share count is {_pct(config.risk.per_trade)} of {sleeve} "
            "divided by the stop distance, rounded down."
        ),
    ]


def _technical_lines(envelope: Envelope) -> list[str]:
    lines = list(envelope.analysis)
    if not lines:
        if envelope.reasons:
            lines.extend(item.message for item in envelope.reasons)
        elif envelope.plan is not None and envelope.plan.setup:
            lines.append(f"{envelope.plan.setup} matched. Readings were not attached.")
        else:
            lines.append("No readings were attached.")
    if envelope.data.errors:
        lines.extend(error_lines(envelope.data.errors))
    lines.extend(_warning_lines(envelope))
    return lines


def _warning_lines(envelope: Envelope) -> list[str]:
    lines: list[str] = []
    for item in envelope.warnings:
        if item.code is ReasonCode.WARN_EXDIV:
            lines.append("Ex-dividend on the entry day. The buy, stop, profit price, and share count stay the same.")
        elif item.code is ReasonCode.WARN_EARNINGS_DISAGREE:
            lines.append("The two earnings calendars disagree by more than 3 sessions. The earlier date is used.")
        elif item.code is ReasonCode.WARN_BAR_RECONSTRUCTED:
            lines.append("The last daily bar was rebuilt from 1-hour bars. Check the close before you buy.")
        elif item.code is ReasonCode.NOTE_ETF_NO_EARNINGS:
            continue
        elif item.code is ReasonCode.SETUP_SUPPRESSED:
            continue
        else:
            lines.append(item.code.value)
    return lines


def _long_actions(envelope: Envelope, config: SwingConfig) -> list[str]:
    if envelope.decision is not DecisionKind.ENTER_LONG or envelope.plan is None:
        return []
    built = envelope.instructions or build_instructions(
        ticker=envelope.ticker,
        plan=envelope.plan,
        config=config,
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


def _user_clock_lines(envelope: Envelope, *, user_tz: str, market_tz: str) -> list[str]:
    lines: list[str] = []
    for stamp in _open_stamps(envelope):
        lines.append(_format_user_stamp(stamp, user_tz=user_tz, market_tz=market_tz))
    return lines


def _market_clock_lines(envelope: Envelope, *, user_tz: str, market_tz: str) -> list[str]:
    del user_tz
    lines: list[str] = []
    for stamp in _open_stamps(envelope):
        formatted = _format_market_stamp(stamp, market_tz=market_tz)
        if formatted is not None:
            lines.append(formatted)
    return lines


def _open_stamps(envelope: Envelope) -> list[str]:
    stamps: list[str] = []
    if envelope.plan is not None and envelope.plan.next_open:
        stamps.append(envelope.plan.next_open)
    data_open = envelope.data.next_open
    if data_open and data_open not in stamps:
        stamps.append(data_open)
    return stamps


def _format_user_stamp(raw: str, *, user_tz: str, market_tz: str) -> str:
    try:
        moment = _parse_instant(raw, market_tz)
        user = moment.astimezone(ZoneInfo(user_tz)).isoformat(timespec="seconds")
    except (ValueError, ZoneInfoNotFoundError, OverflowError, OSError):
        return f"Next open {raw}"
    return f"Next open {user_tz} {user}"


def _format_market_stamp(raw: str, *, market_tz: str) -> str | None:
    try:
        moment = _parse_instant(raw, market_tz)
        market = moment.astimezone(ZoneInfo(market_tz)).isoformat(timespec="seconds")
    except (ValueError, ZoneInfoNotFoundError, OverflowError, OSError):
        return None
    return f"Next open {market_tz} {market}"


def _parse_instant(raw: str, market_tz: str) -> datetime:
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=ZoneInfo(market_tz))
    return moment


def _cents(value: float) -> str:
    quantized = Decimal(str(value)).quantize(_CENTS, rounding=ROUND_HALF_UP)
    return f"{quantized:.2f}"


def _plain(value: float) -> str:
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text or "0"


def _pct(value: float) -> str:
    shown = value * 100
    return f"{_plain(shown)}%"


def _reward(reward_r: float) -> str:
    label = _plain(reward_r)
    if label == "2":
        return "Twice"
    return f"{label} times"
