"""CLI boots: help, JSON envelope, compact default off."""

import json
import subprocess
import sys
from datetime import date

import pytest

from swing.cli import main
from swing.data.models import BarSeries, DailyBar, MarketData
from swing.disclaimer import DISCLAIMER


@pytest.fixture(autouse=True)
def _offline_market(monkeypatch):
    """CLI tests must not call yfinance or Finnhub."""
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
    assert "--compact" in out
    assert "--json" in out


def test_json_stub_is_parseable_and_compact_defaults_off(capsys, monkeypatch):
    monkeypatch.delenv("CONTEXT_DEV_API_KEY", raising=False)
    monkeypatch.delenv("SWING_CONFIG", raising=False)
    code = main(["analyze", "AAPL", "--json"])
    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.out)
    assert captured.out.endswith("\n")
    assert payload["decision"] == "NO_TRADE"
    assert payload["compact"] is False
    assert payload["config_hash"]
    assert payload["disclaimer"] == DISCLAIMER
    assert payload["ticker"] == "AAPL"
    assert "ENTER_SHORT" not in captured.out


def test_compact_text_keeps_reason_gates_and_disclaimer(capsys, monkeypatch):
    monkeypatch.delenv("CONTEXT_DEV_API_KEY", raising=False)
    code = main(["analyze", "AAPL", "--compact"])
    assert code == 0
    text = capsys.readouterr().out
    assert "NO_TRADE" in text
    assert "NO_MARKET_DATA" in text
    assert "missing_api_key" in text
    assert "Not financial advice" in text
    assert "brain not run" not in text
    assert "data_auth=no_trade" in text
    assert "liquidity=not_run" in text


def test_config_compact_is_honored_without_the_flag(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("CONTEXT_DEV_API_KEY", raising=False)
    path = tmp_path / "swing.toml"
    path.write_text("[output]\ncompact = true\n", encoding="utf-8")
    code = main(["analyze", "AAPL", "--json", "--config", str(path)])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["compact"] is True
    assert "Not financial advice" in payload["disclaimer"]


def test_compact_flag_is_opt_in(capsys, monkeypatch):
    monkeypatch.delenv("CONTEXT_DEV_API_KEY", raising=False)
    code = main(["analyze", "AAPL", "--json", "--compact"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["compact"] is True
    assert "Not financial advice" in payload["disclaimer"]


def test_human_output_includes_disclaimer_and_hash(capsys, monkeypatch):
    monkeypatch.delenv("CONTEXT_DEV_API_KEY", raising=False)
    code = main(["analyze", "AAPL"])
    assert code == 0
    text = capsys.readouterr().out
    assert "NO_TRADE" in text
    assert "config_hash" in text
    assert "Not financial advice" in text
    assert "brain not run" not in text
    assert "  data_auth: no_trade" in text


def test_verbose_logs_do_not_pollute_json_stdout(capsys, monkeypatch):
    monkeypatch.delenv("CONTEXT_DEV_API_KEY", raising=False)
    code = main(["analyze", "AAPL", "--json", "--verbose"])
    assert code == 0
    out = capsys.readouterr().out
    json.loads(out)


def test_attached_market_data_stays_no_trade(capsys, monkeypatch):
    monkeypatch.delenv("CONTEXT_DEV_API_KEY", raising=False)
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
    monkeypatch.delenv("CONTEXT_DEV_API_KEY", raising=False)
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
    assert "America/New_York 2026-10-05T09:30:00-04:00" in text
    assert "Europe/London 2026-10-05T14:30:00+01:00" in text
    assert "Africa/Cairo" not in text
    assert "brain not run" not in text
    assert "Not financial advice" in text


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
