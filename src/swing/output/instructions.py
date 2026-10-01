"""Plain-language buy and sell steps for a planned cash long.

The sentences describe the checklist that already ran. They do not add an
exit, a time-stop, or a currency conversion. Money in the sentences is USD.
"""

from __future__ import annotations

import json

from swing.config import SwingConfig
from swing.envelope import Instructions, Plan


def build_instructions(*, ticker: str, plan: Plan, config: SwingConfig | None = None) -> Instructions:
    policy = config or SwingConfig()
    return Instructions(currency="USD", buy=_buy(ticker, plan, policy), sell=_sell(plan, policy))


def compact_buy(ticker: str, plan: Plan) -> str:
    setup = _setup_name(plan)
    return (
        f"Buy: {setup} cash long {plan.size_shares} shares of {ticker} "
        f"at the next NYSE open ({plan.next_open}); entry {_num(plan.entry)} USD. "
        f"Type it in Interactive Brokers. This CLI does not send orders."
    )


def compact_sell(plan: Plan, reward_r: float) -> str:
    reward = _r_label(reward_r)
    return (
        f"Sell: stop {_num(plan.stop)} USD or {reward} target {_num(plan.target)} USD. "
        f"Time-stops are not in v0. Type the exit in Interactive Brokers."
    )


def _buy(ticker: str, plan: Plan, config: SwingConfig) -> str:
    setup = _setup_name(plan)
    equity = ""
    if plan.equity_usd is not None:
        equity = f" Size uses equity {_num(plan.equity_usd)} USD."
    return (
        f"When to buy: {setup} won the mutex (BO_RVOL, then PB_EMA, then RSI2_MR). "
        f"{_signal(setup, config)} "
        f"Buy {plan.size_shares} shares of {ticker} as a cash long. "
        f"Prices are USD.{equity} "
        f"The intended fill is the next NYSE open ({plan.next_open}). "
        f"The planned entry is the signal close, {_num(plan.entry)} USD, "
        f"because the opening print has not happened. "
        f"Type this order in Interactive Brokers yourself. "
        f"This CLI plans the trade and does not send it. "
        f"This is a checklist step, not advice."
    )


def _sell(plan: Plan, config: SwingConfig) -> str:
    reward = _r_label(config.stops.reward_r)
    return (
        f"When to sell: v0 exits this cash long at the stop {_num(plan.stop)} USD "
        f"or the {reward} target {_num(plan.target)} USD. "
        f"The stop is entry minus ATR({config.stops.atr_period}) times {_num(config.stops.atr_multiple)}. "
        f"The target is {reward} above entry, using that same risk. "
        f"BO_RVOL and PB_EMA use that stop and that {reward} target. "
        f"RSI2_MR uses the same stop and {reward} target. "
        f"RSI2_MR's SMA({config.setups.rsi2_mr.sma_trend}) is the entry trend filter, not an exit. "
        f"An SMA(5) exit is not locked in v0. "
        f"Time-stops are not in v0. "
        f"Type the exit in Interactive Brokers yourself. "
        f"This CLI plans the trade and does not send it."
    )


def _signal(setup: str, config: SwingConfig) -> str:
    if setup == "BO_RVOL":
        rule = config.setups.bo_rvol
        return (
            f"The signal means the last close is above SMA({rule.sma_period}), "
            f"above the prior {rule.breakout_lookback}-session high, "
            f"and volume is at least {_num(rule.rvol_min)} times the prior "
            f"{rule.breakout_lookback}-session volume average (today excluded)."
        )
    if setup == "PB_EMA":
        rule = config.setups.pb_ema
        return (
            f"The signal means the last close is above EMA({rule.ema_trend}), "
            f"the low tagged EMA({rule.ema_touch}), "
            f"and the close finished back above that EMA."
        )
    if setup == "RSI2_MR":
        rule = config.setups.rsi2_mr
        return (
            f"The signal means the last close is above SMA({rule.sma_trend}) "
            f"and RSI({rule.rsi_period}) is strictly below {rule.rsi_max}."
        )
    return "The signal is the setup that won the mutex."


def _setup_name(plan: Plan) -> str:
    return plan.setup if plan.setup is not None else "none"


def _r_label(reward_r: float) -> str:
    if reward_r == int(reward_r):
        return f"{int(reward_r)}R"
    return f"{_num(reward_r)}R"


def _num(value: float) -> str:
    return json.dumps(value)
