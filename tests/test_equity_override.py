"""One-run equity override. CLI wins over TOML. The file hash stays the file hash."""

import json
import math
from pathlib import Path

import pytest

from swing.analyze import analyze
from swing.cli import main
from swing.codes import DecisionKind, ReasonCode
from swing.config import SwingConfig
from tests.synthetic import SUMMER_OPEN, equity_config, install_market, quiet_research


@pytest.fixture(autouse=True)
def _offline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SWING_DATA_DIR", str(tmp_path / "swing-data"))
    monkeypatch.delenv("CONTEXT_DEV_API_KEY", raising=False)
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    monkeypatch.delenv("SWING_CONFIG", raising=False)

    def explode(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("equity override tests must not call a market vendor")

    monkeypatch.setattr("swing.analyze.load_market_data", explode)


def _file(tmp_path: Path, equity: float | None) -> Path:
    account = "" if equity is None else f"equity_usd = {equity}\n"
    path = tmp_path / "swing.toml"
    path.write_text(f"[account]\n{account}[research]\nenabled = false\n", encoding="utf-8")
    return path


def _run(argv: list[str]) -> tuple[int, str, str]:
    import io
    from contextlib import redirect_stderr, redirect_stdout

    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


def _shares(equity: float, entry: float, stop: float) -> int:
    return math.floor(equity * 0.01 / (entry - stop))


def test_analyze_help_documents_the_equity_override(capsys):
    try:
        code = main(["analyze", "--help"])
    except SystemExit as exc:
        code = exc.code
    assert code == 0
    text = capsys.readouterr().out
    assert "--equity" in text
    assert "equity_usd" in text
    assert "config_hash" in text
    assert "EQUITY_UNSET" in text


def test_cli_equity_sizes_and_journals_without_changing_the_file_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    install_market(monkeypatch, next_open=SUMMER_OPEN)
    path = _file(tmp_path, 100_000.0)
    file_config = SwingConfig.model_validate(
        {"account": {"equity_usd": 100_000.0}, "research": {"enabled": False}}
    )
    code, text, err = _run(["analyze", "AAPL", "--config", str(path), "--equity", "10000", "--json"])
    assert code == 0
    assert err == ""
    payload = json.loads(text)
    assert payload["decision"] == "ENTER_LONG"
    assert payload["config_hash"] == file_config.config_hash()
    assert payload["config_hash"] != equity_config(10_000.0).config_hash()
    plan = payload["plan"]
    assert plan["entry"] > plan["stop"]
    assert plan["size_shares"] == _shares(10_000.0, plan["entry"], plan["stop"])
    assert plan["size_shares"] < _shares(100_000.0, plan["entry"], plan["stop"])
    assert payload["equity_usd"] == 10_000.0
    assert plan["equity_usd"] == 10_000.0
    record = json.loads((tmp_path / "swing-data" / "journal.jsonl").read_text(encoding="utf-8"))
    assert record["equity_usd"] == 10_000.0
    assert record["size_shares"] == plan["size_shares"]
    assert record["risk_fraction"] == pytest.approx(record["size_shares"] * (record["entry"] - record["stop"]) / 10_000.0)
    assert record["config_hash"] == file_config.config_hash()
    assert "equity=10000.0" in _run(["analyze", "AAPL", "--config", str(path), "--equity", "10000"])[1]


def test_cli_equity_wins_over_toml_and_leaves_indicator_prices_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    install_market(monkeypatch, next_open=SUMMER_OPEN)
    path = _file(tmp_path, 50_000.0)
    file_hash = SwingConfig.model_validate(
        {"account": {"equity_usd": 50_000.0}, "research": {"enabled": False}}
    ).config_hash()
    base_code, base_text, _err = _run(["analyze", "AAPL", "--config", str(path), "--json"])
    over_code, over_text, _err = _run(
        ["analyze", "MSFT", "--config", str(path), "--equity", "10000", "--json"]
    )
    assert base_code == 0 and over_code == 0
    base = json.loads(base_text)
    over = json.loads(over_text)
    assert base["config_hash"] == over["config_hash"] == file_hash
    assert base["plan"]["setup"] == over["plan"]["setup"] == "BO_RVOL"
    assert over["plan"]["entry"] == pytest.approx(base["plan"]["entry"])
    assert over["plan"]["stop"] == pytest.approx(base["plan"]["stop"])
    assert over["plan"]["target"] == pytest.approx(base["plan"]["target"])
    assert base["plan"]["size_shares"] == _shares(50_000.0, base["plan"]["entry"], base["plan"]["stop"])
    assert over["plan"]["size_shares"] == _shares(10_000.0, over["plan"]["entry"], over["plan"]["stop"])
    assert base["equity_usd"] == 50_000.0
    assert over["equity_usd"] == 10_000.0
    lines = (tmp_path / "swing-data" / "journal.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["equity_usd"] == 50_000.0
    assert json.loads(lines[1])["equity_usd"] == 10_000.0
    assert json.loads(lines[1])["risk_fraction"] == pytest.approx(
        json.loads(lines[1])["size_shares"]
        * (json.loads(lines[1])["entry"] - json.loads(lines[1])["stop"])
        / 10_000.0
    )


def test_override_does_not_rescale_open_heat_and_still_blocks_at_one_percent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Heat still adds the 1% new-trade fraction. A smaller --equity does not shrink that fraction."""
    install_market(monkeypatch, next_open=SUMMER_OPEN)
    from swing.journal.paper import PaperJournal
    from tests import synthetic as fixtures

    path = _file(tmp_path, 100_000.0)
    journal = PaperJournal(tmp_path / "swing-data" / "journal.jsonl")
    journal.append(
        fixtures.enter_envelope(ticker="MSFT", size_shares=1100, entry=100.0, stop=95.0),
        equity_usd=100_000.0,
        sector="tech",
    )
    before = journal.path.read_text(encoding="utf-8")
    code, text, _err = _run(
        ["analyze", "AAPL", "--config", str(path), "--equity", "10000", "--sector", "tech", "--json"]
    )
    assert code == 0
    payload = json.loads(text)
    assert payload["decision"] == "NO_TRADE"
    assert payload["reasons"][0]["code"] == "HEAT_LIMIT"
    assert payload["equity_usd"] == 10_000.0
    assert payload["plan"] is None
    assert journal.path.read_text(encoding="utf-8") == before
    _code, text, _err = _run(
        ["analyze", "AAPL", "--config", str(path), "--equity", "10000", "--sector", "tech"]
    )
    assert "HEAT_LIMIT" in text
    assert "equity_usd 10000.0" in text
    assert journal.path.read_text(encoding="utf-8") == before


def test_neither_cli_nor_config_equity_is_still_unset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    install_market(monkeypatch, next_open=SUMMER_OPEN)
    path = _file(tmp_path, None)
    unset = SwingConfig.model_validate({"research": {"enabled": False}})
    code, text, _err = _run(["analyze", "AAPL", "--config", str(path), "--json"])
    assert code == 0
    payload = json.loads(text)
    assert payload["decision"] == "NO_TRADE"
    assert payload["reasons"][0]["code"] == "EQUITY_UNSET"
    assert payload["plan"] is None
    assert payload["equity_usd"] is None
    assert payload["config_hash"] == unset.config_hash()
    assert not (tmp_path / "swing-data" / "journal.jsonl").exists()


def test_cli_equity_alone_is_enough_when_toml_leaves_it_unset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    install_market(monkeypatch, next_open=SUMMER_OPEN)
    path = _file(tmp_path, None)
    unset = SwingConfig.model_validate({"research": {"enabled": False}})
    code, text, _err = _run(["analyze", "AAPL", "--config", str(path), "--equity", "10000", "--json"])
    assert code == 0
    payload = json.loads(text)
    assert payload["decision"] == "ENTER_LONG"
    assert payload["config_hash"] == unset.config_hash()
    assert payload["equity_usd"] == 10_000.0
    assert payload["plan"]["equity_usd"] == 10_000.0
    assert payload["plan"]["size_shares"] == _shares(10_000.0, payload["plan"]["entry"], payload["plan"]["stop"])
    record = json.loads((tmp_path / "swing-data" / "journal.jsonl").read_text(encoding="utf-8"))
    assert record["risk_fraction"] == pytest.approx(
        record["size_shares"] * (record["entry"] - record["stop"]) / 10_000.0
    )


def test_analyze_override_does_not_mutate_config_or_invent_equity():
    cfg = equity_config(100_000.0)
    original_hash = cfg.config_hash()
    entered = analyze(
        "AAPL",
        config=cfg,
        env={},
        equity_usd=10_000.0,
        market=_offline_market(),
        research_result=quiet_research(),
    )
    assert cfg.account.equity_usd == 100_000.0
    assert cfg.config_hash() == original_hash
    assert entered.config_hash == original_hash
    assert entered.decision is DecisionKind.ENTER_LONG
    assert entered.equity_usd == 10_000.0
    assert entered.plan is not None
    assert entered.plan.equity_usd == 10_000.0
    assert entered.plan.size_shares == _shares(10_000.0, entered.plan.entry, entered.plan.stop)
    assert entered.plan.entry == analyze(
        "AAPL",
        config=cfg,
        env={},
        market=_offline_market(),
        research_result=quiet_research(),
    ).plan.entry  # type: ignore[union-attr]

    missing = analyze(
        "AAPL",
        config=equity_config(None),
        env={},
        market=_offline_market(),
        research_result=quiet_research(),
    )
    assert missing.decision is DecisionKind.NO_TRADE
    assert missing.reasons[0].code is ReasonCode.EQUITY_UNSET
    assert missing.equity_usd is None
    assert missing.plan is None


def test_bad_equity_is_usage_and_does_not_invent_a_size(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    install_market(monkeypatch, next_open=SUMMER_OPEN)
    path = _file(tmp_path, 100_000.0)
    for argv in (
        ["analyze", "AAPL", "--config", str(path), "--equity", "-5"],
        ["analyze", "AAPL", "--config", str(path), "--equity=-1"],
        ["analyze", "AAPL", "--config", str(path), "--equity", "nan"],
        ["analyze", "AAPL", "--config", str(path), "--equity", "inf"],
    ):
        with pytest.raises(SystemExit) as exc:
            main(argv)
        assert exc.value.code == 2
    assert not (tmp_path / "swing-data" / "journal.jsonl").exists()
    with pytest.raises(ValueError, match="equity"):
        analyze(
            "AAPL",
            config=equity_config(100_000.0),
            env={},
            equity_usd=float("nan"),
            market=_offline_market(),
            research_result=quiet_research(),
        )


def _offline_market():
    from tests.synthetic import market

    return market(next_open=SUMMER_OPEN)
