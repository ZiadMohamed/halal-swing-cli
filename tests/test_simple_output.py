"""`--simple` is a short human card. JSON stays the full envelope."""

import json
from dataclasses import replace

import pytest

from swing.cli import main
from swing.codes import DecisionKind, ReasonCode
from swing.config import SwingConfig, load_config
from swing.disclaimer import DISCLAIMER
from swing.envelope import DataView, Reason
from swing.output.render import render_simple
from tests.synthetic import SUMMER_OPEN, enter_envelope, install_market, market


def _with_reason(envelope, code: ReasonCode, message: str, **data):
    payload = envelope.model_dump()
    payload["decision"] = DecisionKind.NO_TRADE
    payload["confidence"] = None
    payload["side"] = None
    payload["plan"] = None
    payload["instructions"] = None
    payload["reasons"] = [Reason(code=code, message=message).model_dump()]
    payload["data"] = DataView(**data).model_dump()
    from swing.envelope import Envelope

    return Envelope.model_validate(payload)


@pytest.fixture
def _offline(tmp_path, monkeypatch):
    monkeypatch.setenv("SWING_DATA_DIR", str(tmp_path / "swing-data"))
    monkeypatch.delenv("CONTEXT_DEV_API_KEY", raising=False)
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    monkeypatch.delenv("SWING_CONFIG", raising=False)
    monkeypatch.delenv("SWING_BARS_PROVIDER", raising=False)
    return tmp_path


def test_simple_no_trade_is_one_plain_line_without_the_gate_dump():
    envelope = _with_reason(
        enter_envelope(),
        ReasonCode.NO_MARKET_DATA,
        "No split-adjusted bars are loaded, so the checklist did not run.",
    )
    text = render_simple(envelope)
    assert text == "NO TRADE — no price bars are loaded\n"
    assert "config_hash" not in text
    assert "data_auth" not in text
    assert "NO_MARKET_DATA" not in text
    assert "Not a Shariah certification" not in text


def test_simple_block_names_the_product_lock():
    envelope = _with_reason(
        enter_envelope(),
        ReasonCode.BLOCK_MARGIN,
        "Cash long equity only. This intent is outside the product.",
    )
    envelope = envelope.model_copy(update={"decision": DecisionKind.BLOCK})
    text = render_simple(envelope)
    assert text == "BLOCK — margin accounts are blocked\n"
    assert "config_hash" not in text


def test_simple_unknown_earnings_calendar_names_the_missing_key():
    envelope = _with_reason(
        enter_envelope(),
        ReasonCode.EARNINGS_UNKNOWN,
        "Earnings calendar is unknown and earnings.strict is on.",
        status="partial",
        events_known=False,
        errors=["missing_api_key:FINNHUB_API_KEY"],
    )
    text = render_simple(envelope)
    assert text == "NO TRADE — earnings calendar unknown (set FINNHUB_API_KEY)\n"


def test_simple_earnings_blackout_stays_a_blackout_when_the_calendar_is_known():
    envelope = _with_reason(
        enter_envelope(),
        ReasonCode.EARNINGS_BLACKOUT,
        "Inside the earnings blackout.",
        status="ok",
        events_known=True,
        errors=[],
    )
    text = render_simple(envelope)
    assert text == "NO TRADE — earnings blackout\n"


def test_simple_enter_long_is_a_manual_ibkr_card():
    text = render_simple(enter_envelope(entry=189.5, stop=180.25, target=208.0, size_shares=12))
    assert text == (
        "BUY 12 shares of AAPL at next NYSE open (planned entry $189.50 USD)\n"
        "SELL stop $180.25 USD  OR  target $208.00 USD\n"
        "Place manually in IBKR. Not advice.\n"
    )
    assert "config_hash" not in text
    assert "data_auth" not in text
    assert DISCLAIMER not in text


def test_simple_enter_long_singular_share():
    text = render_simple(enter_envelope(entry=10, stop=9, target=12, size_shares=1))
    assert text.splitlines()[0] == "BUY 1 share of AAPL at next NYSE open (planned entry $10.00 USD)"


def test_cli_simple_without_bars_is_one_plain_line(_offline, monkeypatch, capsys):
    monkeypatch.setattr("swing.analyze.load_market_data", lambda *args, **kwargs: None)
    code = main(["analyze", "AAPL", "--simple"])
    assert code == 0
    text = capsys.readouterr().out
    assert text == "NO TRADE — no price bars are loaded\n"
    assert "config_hash" not in text


def test_cli_simple_unknown_earnings_names_the_missing_key(_offline, monkeypatch, capsys):
    def fake(ticker: str, config, **kwargs):
        del config, kwargs
        if ticker == "SPY":
            return market("SPY", suspect_spy=True)
        base = market(ticker, events_known=False)
        return replace(base, status="partial", errors=("missing_api_key:FINNHUB_API_KEY",))

    monkeypatch.setattr("swing.analyze.load_market_data", fake)
    code = main(["analyze", "AAPL", "--simple"])
    assert code == 0
    assert capsys.readouterr().out == "NO TRADE — earnings calendar unknown (set FINNHUB_API_KEY)\n"


def test_cli_simple_enter_long_works_with_equity(_offline, monkeypatch, capsys):
    install_market(monkeypatch, next_open=SUMMER_OPEN)
    path = _offline / "swing.toml"
    path.write_text("[research]\nenabled = false\n", encoding="utf-8")
    code = main(["analyze", "AAPL", "--simple", "--config", str(path), "--equity", "10000"])
    assert code == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 3
    assert lines[0].startswith("BUY ")
    assert "shares of AAPL at next NYSE open (planned entry $" in lines[0]
    assert lines[0].endswith(" USD)")
    assert lines[1].startswith("SELL stop $")
    assert "  OR  target $" in lines[1]
    assert lines[2] == "Place manually in IBKR. Not advice."
    rendered = "\n".join(lines)
    assert "config_hash" not in rendered
    assert "When to buy" not in rendered
    assert DISCLAIMER not in rendered


def test_cli_simple_json_is_the_full_envelope(_offline, monkeypatch, capsys):
    install_market(monkeypatch, next_open=SUMMER_OPEN)
    path = _offline / "swing.toml"
    path.write_text("[account]\nequity_usd = 100000\n[research]\nenabled = false\n", encoding="utf-8")
    file_config = SwingConfig.model_validate(
        {"account": {"equity_usd": 100000}, "research": {"enabled": False}}
    )
    code = main(["analyze", "AAPL", "--json", "--simple", "--config", str(path), "--equity", "10000"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"] == "ENTER_LONG"
    assert payload["disclaimer"] == DISCLAIMER
    assert payload["config_hash"] == file_config.config_hash()
    assert payload["config_hash"] != SwingConfig.model_validate(
        {"account": {"equity_usd": 10000}, "research": {"enabled": False}}
    ).config_hash()
    assert payload["equity_usd"] == 10000
    assert payload["plan"]["size_shares"] >= 1
    assert payload["instructions"]["currency"] == "USD"
    assert payload["gates"]
    assert "NO TRADE —" not in json.dumps(payload)


def test_cli_loads_cwd_dotenv_before_config(_offline, monkeypatch, capsys):
    monkeypatch.chdir(_offline)
    (_offline / ".env").write_text("SWING_BARS_PROVIDER=massive\n", encoding="utf-8")
    seen: dict[str, str] = {}

    def wrapped(path=None, env=None):
        cfg = load_config(path=path, env=env)
        seen["provider"] = cfg.data.bars_provider
        return cfg

    monkeypatch.setattr("swing.cli.load_config", wrapped)
    monkeypatch.setattr("swing.analyze.load_market_data", lambda *args, **kwargs: None)
    code = main(["analyze", "AAPL", "--simple"])
    assert code == 0
    assert seen["provider"] == "massive"
    assert capsys.readouterr().out.startswith("NO TRADE —")


def test_cli_dotenv_does_not_override_the_shell(_offline, monkeypatch):
    monkeypatch.chdir(_offline)
    (_offline / ".env").write_text("SWING_BARS_PROVIDER=massive\n", encoding="utf-8")
    monkeypatch.setenv("SWING_BARS_PROVIDER", "yfinance")
    seen: dict[str, str] = {}

    def wrapped(path=None, env=None):
        cfg = load_config(path=path, env=env)
        seen["provider"] = cfg.data.bars_provider
        return cfg

    monkeypatch.setattr("swing.cli.load_config", wrapped)
    monkeypatch.setattr("swing.analyze.load_market_data", lambda *args, **kwargs: None)
    code = main(["analyze", "AAPL", "--json"])
    assert code == 0
    assert seen["provider"] == "yfinance"
