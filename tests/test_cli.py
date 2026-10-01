"""CLI boots: help, JSON envelope, compact default off."""

import json
import subprocess
import sys

from swing.cli import main
from swing.disclaimer import DISCLAIMER


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


def test_verbose_logs_do_not_pollute_json_stdout(capsys, monkeypatch):
    monkeypatch.delenv("CONTEXT_DEV_API_KEY", raising=False)
    code = main(["analyze", "AAPL", "--json", "--verbose"])
    assert code == 0
    out = capsys.readouterr().out
    json.loads(out)


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
