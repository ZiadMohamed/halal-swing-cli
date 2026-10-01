"""USD checklist text for a manual IBKR cash long. Offline fixtures only."""

import json
from pathlib import Path

import pytest

from swing.cli import main
from swing.config import SwingConfig
from swing.disclaimer import DISCLAIMER
from swing.envelope import Envelope
from swing.output.render import render_text
from tests.synthetic import SUMMER_OPEN, install_market
from tests.test_render import _envelope


def _run(argv: list[str]) -> tuple[int, str, str]:
    import io
    from contextlib import redirect_stderr, redirect_stdout

    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


@pytest.fixture
def _offline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SWING_DATA_DIR", str(tmp_path / "swing-data"))
    monkeypatch.delenv("CONTEXT_DEV_API_KEY", raising=False)
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    monkeypatch.delenv("SWING_CONFIG", raising=False)
    install_market(monkeypatch, next_open=SUMMER_OPEN)
    path = tmp_path / "swing.toml"
    path.write_text("[research]\nenabled = false\n", encoding="utf-8")
    return path


def test_analyze_equity_text_states_when_to_buy_and_sell_in_usd(_offline: Path):
    code, text, err = _run(["analyze", "AAPL", "--config", str(_offline), "--equity", "10000"])
    assert code == 0
    assert err == ""
    assert "AAPL  ENTER_LONG" in text
    assert text.rstrip("\n").endswith(DISCLAIMER)
    assert "When to buy:" in text
    assert "When to sell:" in text
    buy, sell = _buy_sell(text)
    assert "BO_RVOL" in buy
    assert "mutex" in buy
    assert "SMA(50)" in buy
    assert "20-session" in buy
    assert "1.5" in buy
    assert "cash long" in buy
    assert "USD" in buy
    assert "10000.0 USD" in buy
    assert "next NYSE open" in buy
    assert SUMMER_OPEN in buy
    assert "signal close" in buy
    assert "Interactive Brokers" in buy
    assert "does not send" in buy
    assert "not advice" in buy
    assert "USD" in sell
    assert "2R" in sell
    assert "ATR(14)" in sell
    assert "1.5" in sell
    assert "BO_RVOL" in sell
    assert "PB_EMA" in sell
    assert "RSI2_MR" in sell
    assert "SMA(200)" in sell
    assert "An SMA(5) exit is not locked in v0." in sell
    assert "Time-stops are not in v0." in sell
    assert "Interactive Brokers" in sell
    assert "does not send" in sell
    assert "EUR" not in text
    assert "GBP" not in text
    plan = _plan_numbers(text)
    assert f"{plan['size']} shares" in buy or f"Buy {plan['size']} shares" in buy
    assert f"{plan['entry']} USD" in buy
    assert f"{plan['stop']} USD" in sell
    assert f"{plan['target']} USD" in sell
    assert "entry=" in text and "USD" in text
    assert f"stop={plan['stop']} USD" in text
    assert f"target={plan['target']} USD" in text


def test_compact_analyze_text_is_shorter_and_still_says_buy_and_sell(_offline: Path):
    _code, full, _err = _run(["analyze", "AAPL", "--config", str(_offline), "--equity", "10000"])
    code, compact, err = _run(
        ["analyze", "AAPL", "--config", str(_offline), "--equity", "10000", "--compact"]
    )
    assert code == 0
    assert err == ""
    assert "Buy:" in compact
    assert "Sell:" in compact
    assert "When to buy:" not in compact
    assert "When to sell:" not in compact
    assert "BO_RVOL" in compact
    assert "cash long" in compact
    assert "USD" in compact
    assert "next NYSE open" in compact
    assert SUMMER_OPEN in compact
    assert "2R" in compact
    assert "Time-stops are not in v0." in compact
    assert "Interactive Brokers" in compact
    assert "does not send" in compact
    assert compact.rstrip("\n").endswith(DISCLAIMER)
    assert len(compact) < len(full)


def test_json_adds_buy_and_sell_without_a_schema_bump_or_a_new_hash(_offline: Path):
    file_hash = SwingConfig.model_validate({"research": {"enabled": False}}).config_hash()
    code, raw, err = _run(["analyze", "AAPL", "--config", str(_offline), "--equity", "10000", "--json"])
    assert code == 0
    assert err == ""
    payload = json.loads(raw)
    assert payload["schema_version"] == "1.1.0"
    assert payload["confidence"] == "checklist_only"
    assert payload["config_hash"] == file_hash
    assert payload["equity_usd"] == 10000.0
    instructions = payload["instructions"]
    assert instructions["currency"] == "USD"
    assert instructions["buy"].startswith("When to buy:")
    assert instructions["sell"].startswith("When to sell:")
    assert "BO_RVOL" in instructions["buy"]
    assert str(payload["plan"]["size_shares"]) in instructions["buy"]
    assert "USD" in instructions["buy"]
    assert "USD" in instructions["sell"]
    assert "2R" in instructions["sell"]
    assert "not in v0" in instructions["sell"]
    assert "Interactive Brokers" in instructions["buy"]
    journal = json.loads((_offline.parent / "swing-data" / "journal.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert "instructions" not in journal
    assert journal["equity_usd"] == 10000.0
    assert journal["config_hash"] == file_hash


def test_no_trade_does_not_print_buy_or_sell_instructions(_offline: Path):
    code, text, err = _run(["analyze", "AAPL", "--config", str(_offline)])
    assert code == 0
    assert err == ""
    assert "NO_TRADE" in text
    assert "EQUITY_UNSET" in text
    assert "When to buy:" not in text
    assert "When to sell:" not in text
    assert "Buy:" not in text
    assert "Sell:" not in text
    _code, raw, _err = _run(["analyze", "AAPL", "--config", str(_offline), "--json"])
    payload = json.loads(raw)
    assert payload["instructions"] is None
    assert payload["plan"] is None


def test_help_says_usd_only_and_that_ibkr_orders_are_typed_by_hand(capsys):
    try:
        code = main(["analyze", "--help"])
    except SystemExit as exc:
        code = exc.code
    assert code == 0
    text = capsys.readouterr().out
    assert "USD" in text
    assert "Interactive Brokers" in text
    assert "does not send" in text
    assert "cash long" in text.lower() or "cash-long" in text.lower()


def test_readme_documents_usd_manual_ibkr_and_buy_sell():
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "## How to use the plan (manual IBKR)" in readme
    section = readme.split("## How to use the plan (manual IBKR)", 1)[1]
    assert "USD" in section
    assert "Interactive Brokers" in section
    assert "does not send" in section
    assert "When to buy" in section
    assert "When to sell" in section
    assert "cash long" in section.lower()
    assert "next NYSE open" in section
    assert "2R" in section
    assert "Time-stops" in section
    assert "not in v0" in section
    assert "SMA(5)" in section
    assert "checklist_only" in section
    assert "Not financial advice" in readme
    assert "EUR" not in readme
    assert "GBP" not in readme


def test_pb_and_rsi2_text_names_the_locked_signal_and_does_not_invent_an_exit():
    pb = render_text(
        _envelope(
            plan={
                "side": "long",
                "setup": "PB_EMA",
                "entry": 50.0,
                "stop": 48.0,
                "target": 54.0,
                "size_shares": 8,
                "equity_usd": 10000.0,
                "next_open": SUMMER_OPEN,
            }
        )
    )
    pb_buy, pb_sell = _buy_sell(pb)
    assert "PB_EMA" in pb_buy
    assert "EMA(50)" in pb_buy
    assert "EMA(20)" in pb_buy
    assert "8 shares" in pb_buy
    assert "50.0 USD" in pb_buy
    assert "48.0 USD" in pb_sell
    assert "54.0 USD" in pb_sell
    assert "2R" in pb_sell
    assert "An SMA(5) exit is not locked in v0." in pb_sell
    assert "Time-stops are not in v0." in pb_sell

    rsi = render_text(
        _envelope(
            plan={
                "side": "long",
                "setup": "RSI2_MR",
                "entry": 10.0,
                "stop": 9.0,
                "target": 12.0,
                "size_shares": 3,
                "equity_usd": 10000.0,
                "next_open": SUMMER_OPEN,
            }
        )
    )
    rsi_buy, rsi_sell = _buy_sell(rsi)
    assert "RSI2_MR" in rsi_buy
    assert "SMA(200)" in rsi_buy
    assert "RSI(2)" in rsi_buy
    assert "below 10" in rsi_buy
    assert "3 shares" in rsi_buy
    assert "10.0 USD" in rsi_buy
    assert "9.0 USD" in rsi_sell
    assert "12.0 USD" in rsi_sell
    assert "An SMA(5) exit is not locked in v0." in rsi_sell
    assert "Time-stops are not in v0." in rsi_sell
    assert "sell at SMA(5)" not in rsi.lower()


def test_signal_wording_follows_the_config_periods_without_touching_the_hash(
    _offline: Path,
):
    custom = SwingConfig.model_validate(
        {
            "research": {"enabled": False},
            "setups": {"bo_rvol": {"sma_period": 40, "rvol_min": 1.8, "breakout_lookback": 15}},
        }
    )
    _offline.write_text(
        "\n".join(
            [
                "[research]",
                "enabled = false",
                "[setups.bo_rvol]",
                "sma_period = 40",
                "rvol_min = 1.8",
                "breakout_lookback = 15",
                "",
            ]
        ),
        encoding="utf-8",
    )
    code, text, err = _run(["analyze", "AAPL", "--config", str(_offline), "--equity", "10000"])
    assert code == 0
    assert err == ""
    buy, _sell = _buy_sell(text)
    assert "SMA(40)" in buy
    assert "SMA(50)" not in buy
    assert "15-session" in buy
    assert "1.8" in buy
    _json_code, raw, _json_err = _run(
        ["analyze", "AAPL", "--config", str(_offline), "--equity", "10000", "--json"]
    )
    assert _json_code == 0
    payload = json.loads(raw)
    assert payload["config_hash"] == custom.config_hash()
    assert payload["schema_version"] == "1.1.0"
    assert Envelope.model_fields["schema_version"].default == "1.1.0"


def _buy_sell(text: str) -> tuple[str, str]:
    buy = next(line for line in text.splitlines() if line.startswith("When to buy:"))
    sell = next(line for line in text.splitlines() if line.startswith("When to sell:"))
    return buy, sell


def _plan_numbers(text: str) -> dict[str, str]:
    line = next(item for item in text.splitlines() if item.startswith("plan "))
    fields = {}
    for token in line.split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        fields[key] = value.removesuffix("USD").strip()
    return fields
