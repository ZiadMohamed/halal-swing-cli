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
    path.write_text("", encoding="utf-8")
    return path


def test_card_states_the_plan_in_usd(_offline: Path):
    code, text, err = _run(["analyze", "AAPL", "--config", str(_offline), "--equity", "10000"])
    assert code == 0
    assert err == ""
    assert "AAPL  ENTER_LONG" in text
    assert "config_hash" in text
    assert text.rstrip("\n").endswith(DISCLAIMER)
    plan = _plan_numbers(text)
    assert plan["setup"] == "BO_RVOL"
    assert "USD" in text
    assert "EUR" not in text
    assert "GBP" not in text
    assert f"equity={plan['equity']} USD" in text or "10000.0" in text
    assert SUMMER_OPEN in text
    buy = next(line for line in text.splitlines() if line.startswith("Buy:"))
    sell = next(line for line in text.splitlines() if line.startswith("Sell:"))
    assert plan["size"] in buy
    assert plan["entry"] in buy
    assert plan["stop"] in sell
    assert plan["target"] in sell
    assert "does not send" in text
    assert "When to buy:" not in text


def test_explain_is_longer_and_names_the_gates(_offline: Path):
    _code, card, _err = _run(["analyze", "AAPL", "--config", str(_offline), "--equity", "10000"])
    code, explained, err = _run(["analyze", "AAPL", "--config", str(_offline), "--equity", "10000", "--explain"])
    assert code == 0
    assert err == ""
    assert "When to buy:" in explained
    assert "When to sell:" in explained
    assert "  setup_mutex: pass" in explained
    assert explained.rstrip("\n").endswith(DISCLAIMER)
    assert len(explained) > len(card)
    assert _plan_numbers(explained) == _plan_numbers(card)


def test_json_adds_buy_and_sell_and_keeps_the_file_hash(_offline: Path):
    file_hash = SwingConfig().config_hash()
    code, raw, err = _run(["analyze", "AAPL", "--config", str(_offline), "--equity", "10000", "--json"])
    assert code == 0
    assert err == ""
    payload = json.loads(raw)
    assert payload["schema_version"] == "2.0.0"
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
    assert not (_offline.parent / "swing-data" / "journal.jsonl").exists()


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


def test_pb_and_rsi2_cards_name_the_setup_and_the_prices():
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
    assert "setup=PB_EMA" in pb
    assert "entry=50.0" in pb
    assert "stop=48.0" in pb
    assert "target=54.0" in pb
    assert "size=8" in pb
    assert "sell at SMA(5)" not in pb.lower()

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
    assert "setup=RSI2_MR" in rsi
    assert "size=3" in rsi
    assert "entry=10.0" in rsi
    assert "stop=9.0" in rsi
    assert "target=12.0" in rsi


def test_signal_wording_follows_the_config_periods_without_touching_the_hash(
    _offline: Path,
):
    custom = SwingConfig.model_validate(
        {"setups": {"bo_rvol": {"sma_period": 40, "rvol_min": 1.8, "breakout_lookback": 15}}}
    )
    _offline.write_text(
        "\n".join(
            [
                "[setups.bo_rvol]",
                "sma_period = 40",
                "rvol_min = 1.8",
                "breakout_lookback = 15",
                "",
            ]
        ),
        encoding="utf-8",
    )
    code, text, err = _run(["analyze", "AAPL", "--config", str(_offline), "--equity", "10000", "--explain"])
    assert code == 0
    assert err == ""
    buy = next(line for line in text.splitlines() if line.startswith("When to buy:"))
    assert "SMA(40)" in buy
    assert "15-session" in buy
    assert "1.8" in buy
    _json_code, raw, _json_err = _run(
        ["analyze", "AAPL", "--config", str(_offline), "--equity", "10000", "--json"]
    )
    assert _json_code == 0
    payload = json.loads(raw)
    assert payload["config_hash"] == custom.config_hash()
    assert payload["schema_version"] == "2.0.0"
    assert Envelope.model_fields["schema_version"].default == "2.0.0"


def _plan_numbers(text: str) -> dict[str, str]:
    line = next(item for item in text.splitlines() if item.startswith("plan "))
    fields = {}
    for token in line.split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        fields[key] = value.removesuffix("USD").strip()
    return fields
