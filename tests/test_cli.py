"""CLI boots: help, JSON envelope, card by default, gates on --explain."""

import json
import subprocess
import sys
from datetime import date

import pytest

from swing.cli import main
from swing.data.models import BarSeries, DailyBar, MarketData
from swing.disclaimer import DISCLAIMER


@pytest.fixture(autouse=True)
def _offline_market(tmp_path, monkeypatch):
    """CLI tests must not call yfinance or Finnhub, or read a home-directory journal."""
    monkeypatch.setenv("SWING_DATA_DIR", str(tmp_path / "swing-data"))
    monkeypatch.setattr("swing.analyze.load_market_data", lambda *args, **kwargs: None)


def test_analyze_help_exits_zero(capsys):
    try:
        code = main(["analyze", "--help"])
    except SystemExit as exc:
        code = exc.code
    assert code == 0
    out = capsys.readouterr().out
    assert "analyze" in out
    assert "Not financial advice" in out
    assert "--explain" in out
    assert "--json" in out
    assert "--simple" in out
    assert "--verbose" in out
    assert "--compact" not in out
    assert "--sector" in out


def test_json_is_parseable_and_carries_the_decision(capsys, monkeypatch):
    monkeypatch.delenv("SWING_CONFIG", raising=False)
    code = main(["analyze", "AAPL", "--json"])
    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.out)
    assert captured.out.endswith("\n")
    assert payload["schema_version"] == "2.0.0"
    assert payload["decision"] == "NO_TRADE"
    assert payload["reasons"][0]["code"] == "NO_MARKET_DATA"
    assert payload["plan"] is None
    assert payload["config_hash"]
    assert payload["disclaimer"] == DISCLAIMER
    assert payload["ticker"] == "AAPL"
    assert "research" not in payload
    assert "ENTER_SHORT" not in captured.out


def test_card_hides_gates_and_explain_shows_them(capsys, monkeypatch):
    monkeypatch.delenv("SWING_CONFIG", raising=False)
    code = main(["analyze", "AAPL"])
    assert code == 0
    card = capsys.readouterr().out
    assert "NO TRADE" in card
    assert "No split-adjusted bars" in card
    assert "config_hash" not in card
    assert "Not financial advice" not in card
    assert "data_auth:" not in card

    code = main(["analyze", "AAPL", "--explain"])
    assert code == 0
    explained = capsys.readouterr().out
    assert "No split-adjusted bars" in explained
    assert "  data_auth: no_trade" in explained
    assert "config_hash" in explained
    assert "  liquidity: not_run" in explained
    assert explained.endswith(DISCLAIMER + "\n")


def test_default_card_omits_the_hash_and_verbose_prints_them(capsys, monkeypatch):
    monkeypatch.delenv("SWING_CONFIG", raising=False)
    code = main(["analyze", "AAPL"])
    assert code == 0
    text = capsys.readouterr().out
    assert "NO TRADE" in text
    assert "config_hash" not in text
    assert "Not financial advice" not in text
    assert "brain not run" not in text
    code = main(["analyze", "AAPL", "--verbose"])
    assert code == 0
    verbose = capsys.readouterr().out
    assert "config_hash" in verbose
    assert "Not financial advice" in verbose


def test_simple_prints_the_same_card_as_the_default(capsys, monkeypatch):
    monkeypatch.delenv("SWING_CONFIG", raising=False)
    assert main(["analyze", "AAPL"]) == 0
    default = capsys.readouterr().out
    assert main(["analyze", "AAPL", "--simple"]) == 0
    assert capsys.readouterr().out == default


def test_verbose_logs_do_not_pollute_json_stdout(capsys, monkeypatch):
    monkeypatch.delenv("SWING_CONFIG", raising=False)
    code = main(["analyze", "AAPL", "--json", "--verbose"])
    assert code == 0
    out = capsys.readouterr().out
    json.loads(out)


def test_attached_market_data_stays_no_trade(capsys, monkeypatch):
    monkeypatch.delenv("SWING_CONFIG", raising=False)
    market = MarketData(
        ticker="AAPL",
        status="ok",
        bars_provider="yfinance",
        events_provider="finnhub",
        bars=BarSeries(
            ticker="AAPL",
            provider="yfinance",
            bars=(
                DailyBar(
                    session=date(2026, 9, 30),
                    open=1,
                    high=1,
                    low=1,
                    close=1,
                    volume=1,
                    raw_close=1,
                ),
            ),
            corp_action_suspect=False,
            corp_action_reasons=(),
            adjustment="split_and_dividend",
        ),
        earnings=(),
        dividends=(),
        next_open="2026-10-02T09:30:00-04:00",
        errors=(),
    )
    monkeypatch.setattr("swing.analyze.load_market_data", lambda *args, **kwargs: market)
    code = main(["analyze", "AAPL", "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"] == "NO_TRADE"
    assert payload["plan"] is None
    assert payload["data"]["status"] == "ok"
    assert payload["data"]["bar_count"] == 1
    assert payload["data"]["corp_action_suspect"] is False
    assert payload["data"]["next_open"] == "2026-10-02T09:30:00-04:00"
    assert "ENTER_SHORT" not in json.dumps(payload)
    assert payload["confidence"] is None


def test_text_uses_the_configured_user_clock(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("SWING_CONFIG", raising=False)
    path = tmp_path / "swing.toml"
    path.write_text('[timezone]\nuser = "Europe/London"\n', encoding="utf-8")
    market = MarketData(
        ticker="AAPL",
        status="ok",
        bars_provider="yfinance",
        events_provider="finnhub",
        bars=BarSeries(
            ticker="AAPL",
            provider="yfinance",
            bars=(
                DailyBar(
                    session=date(2026, 10, 2),
                    open=1,
                    high=1,
                    low=1,
                    close=1,
                    volume=1,
                    raw_close=1,
                ),
            ),
            corp_action_suspect=False,
            corp_action_reasons=(),
            adjustment="split_and_dividend",
        ),
        earnings=(),
        dividends=(),
        next_open="2026-10-05T09:30:00-04:00",
        errors=(),
    )
    monkeypatch.setattr("swing.analyze.load_market_data", lambda *args, **kwargs: market)
    code = main(["analyze", "AAPL", "--config", str(path)])
    assert code == 0
    text = capsys.readouterr().out
    assert "Next open Europe/London 2026-10-05T14:30:00+01:00" in text
    assert "America/New_York" not in text
    assert "Africa/Cairo" not in text
    assert "brain not run" not in text
    assert "Not financial advice" not in text


def test_bad_ticker_exits_2(capsys):
    code = main(["analyze", "!!!", "--json"])
    assert code == 2
    err = capsys.readouterr().err
    assert err


def test_module_help_subprocess():
    result = subprocess.run(
        [sys.executable, "-m", "swing", "analyze", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Not financial advice" in result.stdout
    assert "analyze" in result.stdout
