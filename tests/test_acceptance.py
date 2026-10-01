"""Offline acceptance: decisions, warnings, clocks, and the paper book the CLI reads."""

import json
from datetime import date
from pathlib import Path

import pytest

from swing.cli import main
from swing.codes import DecisionKind, ReasonCode
from swing.config import SwingConfig
from swing.data.models import DividendEvent, EarningsEvent
from swing.disclaimer import DISCLAIMER
from swing.journal.paper import PaperJournal
from tests import synthetic as fixtures
from tests.synthetic import (
    CAIRO_SUMMER,
    CAIRO_WINTER,
    NY_SUMMER,
    NY_WINTER,
    SUMMER_OPEN,
    WINTER_OPEN,
    equity_config,
    install_market,
    quiet_research,
)

DEFAULT_HASH = "6aee6dc8f4b494c5b4e3f81821fe9b3ae7f9ef8944b12ee8e7d8a8a0f49da0b5"


@pytest.fixture(autouse=True)
def _offline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SWING_DATA_DIR", str(tmp_path / "swing-data"))
    monkeypatch.delenv("CONTEXT_DEV_API_KEY", raising=False)
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    monkeypatch.delenv("SWING_CONFIG", raising=False)

    def explode(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("acceptance tests must not call a market vendor")

    monkeypatch.setattr("swing.analyze.load_market_data", explode)


def _config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "swing.toml"
    path.write_text(body, encoding="utf-8")
    return path


def _equity_config(tmp_path: Path, equity: float | None = 100_000.0) -> Path:
    account = "equity_usd = 100000\n" if equity is not None else ""
    if equity is not None and equity != 100_000.0:
        account = f"equity_usd = {equity}\n"
    return _config(
        tmp_path,
        f"[account]\n{account}[research]\nenabled = false\n",
    )


def _run(argv: list[str]) -> tuple[int, str, str]:
    import io
    from contextlib import redirect_stderr, redirect_stdout

    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


def test_default_config_hash_stays_on_the_chat4_digest():
    assert SwingConfig().config_hash() == DEFAULT_HASH


def test_renderer_does_not_write_the_journal():
    source = Path("src/swing/output/render.py").read_text(encoding="utf-8")
    assert "PaperJournal" not in source
    assert "journal_path" not in source
    assert "journal.jsonl" not in source


def test_enter_long_is_journaled_and_prints_summer_clocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    install_market(monkeypatch, next_open=SUMMER_OPEN)
    config = _equity_config(tmp_path)
    code, text, _err = _run(["analyze", "AAPL", "--config", str(config)])
    assert code == 0
    assert "AAPL  ENTER_LONG" in text
    assert f"next_open America/New_York {NY_SUMMER}" in text
    assert f"next_open Africa/Cairo {CAIRO_SUMMER}" in text
    assert "  data_auth: pass" in text
    assert text.rstrip("\n").endswith(DISCLAIMER)
    path = tmp_path / "swing-data" / "journal.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["decision"] == "ENTER_LONG"
    assert record["ticker"] == "AAPL"
    assert record["size_shares"] >= 1
    equity = 100_000.0
    assert record["risk_fraction"] == pytest.approx(
        record["size_shares"] * (record["entry"] - record["stop"]) / equity
    )
    assert record["equity_usd"] == equity

    code2, text2, _err2 = _run(["analyze", "AAPL", "--config", str(config)])
    assert code2 == 0
    assert "ENTER_LONG" in text2
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2
    assert path.read_bytes().splitlines()[0] == lines[0].encode("utf-8")


def test_winter_open_prints_new_york_and_cairo_standard_offsets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    install_market(monkeypatch, next_open=WINTER_OPEN)
    code, text, _err = _run(["analyze", "AAPL", "--config", str(_equity_config(tmp_path))])
    assert code == 0
    assert "ENTER_LONG" in text
    assert f"next_open America/New_York {NY_WINTER}" in text
    assert f"next_open Africa/Cairo {CAIRO_WINTER}" in text
    assert "+03:00" not in text


def test_no_trade_and_block_do_not_append(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    install_market(
        monkeypatch,
        next_open=SUMMER_OPEN,
        earnings=(EarningsEvent(ticker="AAPL", report_date=date(2026, 10, 5), hour="bmo"),),
    )
    code, text, _err = _run(["analyze", "AAPL", "--config", str(_equity_config(tmp_path))])
    assert code == 0
    assert "NO_TRADE" in text
    assert "EARNINGS_BLACKOUT" in text
    assert not (tmp_path / "swing-data" / "journal.jsonl").exists()

    unset = _config(tmp_path, "[research]\nenabled = false\n")
    install_market(monkeypatch, next_open=SUMMER_OPEN)
    code, text, _err = _run(["analyze", "AAPL", "--config", str(unset)])
    assert code == 0
    assert "AAPL  NO_TRADE" in text
    assert "EQUITY_UNSET" in text
    assert not (tmp_path / "swing-data" / "journal.jsonl").exists()

    blocked = _config(tmp_path, '[account]\nmode = "margin"\n[research]\nenabled = false\n')
    code, text, _err = _run(["analyze", "AAPL", "--config", str(blocked)])
    assert code == 0
    assert "AAPL  BLOCK" in text
    assert "BLOCK_MARGIN" in text
    assert not (tmp_path / "swing-data" / "journal.jsonl").exists()


def test_warn_exdiv_and_spy_r2_still_journal_the_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    install_market(
        monkeypatch,
        next_open=SUMMER_OPEN,
        include_spy=True,
        dividends=(DividendEvent(ticker="AAPL", ex_date=date(2026, 10, 5), amount=0.20, currency="USD"),),
    )
    code, text, _err = _run(["analyze", "aapl", "--config", str(_equity_config(tmp_path)), "--json"])
    assert code == 0
    payload = json.loads(text)
    assert payload["decision"] == DecisionKind.ENTER_LONG.value
    codes = {item["code"] for item in payload["warnings"]}
    assert ReasonCode.WARN_EXDIV.value in codes
    assert ReasonCode.WARN_SPY_R2.value in codes
    assert payload["plan"]["size_shares"] >= 1
    assert payload["shariah"]["screened"] is False
    assert payload["research"]["affects_checklist_math"] is False
    record = json.loads((tmp_path / "swing-data" / "journal.jsonl").read_text(encoding="utf-8"))
    assert record["size_shares"] == payload["plan"]["size_shares"]
    assert record["entry"] == payload["plan"]["entry"]
    assert record["stop"] == payload["plan"]["stop"]
    assert record["risk_fraction"] == pytest.approx(
        record["size_shares"] * (record["entry"] - record["stop"]) / 100_000.0
    )


def test_cli_enforces_heat_sector_heat_and_max_positions_from_the_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    install_market(monkeypatch, next_open=SUMMER_OPEN)
    data = tmp_path / "swing-data"
    data.mkdir()
    journal = PaperJournal(data / "journal.jsonl")
    config = _equity_config(tmp_path)

    for ticker in ("MSFT", "NVDA", "AMZN"):
        journal.append(fixtures.enter_envelope(ticker=ticker, size_shares=400), equity_usd=100_000.0, sector=ticker)
    code, text, _err = _run(["analyze", "AAPL", "--config", str(config), "--json"])
    assert code == 0
    payload = json.loads(text)
    assert payload["decision"] == "NO_TRADE"
    assert payload["reasons"][0]["code"] == "HEAT_LIMIT"
    assert len(journal.path.read_text(encoding="utf-8").splitlines()) == 3

    journal.path.write_text("", encoding="utf-8")
    journal.append(fixtures.enter_envelope(ticker="MSFT", size_shares=500), equity_usd=100_000.0, sector="tech")
    code, text, _err = _run(["analyze", "AAPL", "--config", str(config), "--sector", "tech", "--json"])
    payload = json.loads(text)
    assert payload["decision"] == "NO_TRADE"
    assert payload["reasons"][0]["code"] == "HEAT_LIMIT"
    assert "sector" in payload["reasons"][0]["message"].lower()
    assert len(journal.load_positions()) == 1

    code, text, _err = _run(["analyze", "AAPL", "--config", str(config), "--json"])
    payload = json.loads(text)
    assert payload["decision"] == "ENTER_LONG"
    assert len(journal.load_positions()) == 2

    journal.path.unlink()
    for index in range(4):
        journal.append(
            fixtures.enter_envelope(ticker=f"T{index}", size_shares=20),
            equity_usd=100_000.0,
            sector=None,
        )
    code, text, _err = _run(["analyze", "AAPL", "--config", str(config), "--json"])
    payload = json.loads(text)
    assert payload["decision"] == "NO_TRADE"
    assert payload["reasons"][0]["code"] == "MAX_POSITIONS"
    assert len(journal.load_positions()) == 4


def test_a_corrupt_journal_refuses_to_analyze(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    install_market(monkeypatch, next_open=SUMMER_OPEN)
    data = tmp_path / "swing-data"
    data.mkdir()
    (data / "journal.jsonl").write_text("{not json}\n", encoding="utf-8")
    code, _out, err = _run(["analyze", "AAPL", "--config", str(_equity_config(tmp_path))])
    assert code == 2
    assert "journal" in err.lower()
    assert _out == ""


def test_analyze_without_equity_still_refuses_to_invent_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    install_market(monkeypatch)
    from swing.analyze import analyze

    envelope = analyze(
        "AAPL",
        config=equity_config(None),
        env={},
        fetch_market=True,
        research_result=quiet_research(),
    )
    assert envelope.decision is DecisionKind.NO_TRADE
    assert envelope.reasons[0].code is ReasonCode.EQUITY_UNSET
    assert envelope.plan is None
