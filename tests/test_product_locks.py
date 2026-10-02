"""Cash, long equity only. No broker library and no short decision."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from swing.analyze import analyze
from swing.codes import DecisionKind, ReasonCode
from swing.config import SwingConfig
from swing.journal.paper import PaperJournal

_ROOT = Path(__file__).resolve().parents[1]
_FORBIDDEN_LOCK_NAMES = ("ib-insync", "ib_insync", "ib_async", "ibapi")


def test_there_is_no_enter_short_decision():
    names = set(DecisionKind.__members__) | set(ReasonCode.__members__)
    assert "ENTER_SHORT" not in names
    assert "BLOCK" not in DecisionKind.__members__
    assert DecisionKind.ENTER_LONG.value == "ENTER_LONG"
    source = "\n".join(path.read_text(encoding="utf-8") for path in (_ROOT / "src").rglob("*.py"))
    assert "ENTER_SHORT" not in source


def test_lockfile_has_no_broker_or_order_library():
    lock = (_ROOT / "uv.lock").read_text(encoding="utf-8").lower()
    for name in _FORBIDDEN_LOCK_NAMES:
        assert name not in lock


def test_margin_mode_is_rejected_when_config_loads():
    with pytest.raises(ValidationError):
        SwingConfig.model_validate({"account": {"mode": "margin"}})
    assert SwingConfig().account.mode == "cash"


def test_shariah_screen_cannot_be_turned_on():
    with pytest.raises(ValidationError):
        SwingConfig.model_validate({"shariah": {"screen_in_v0": True}})
    with pytest.raises(ValidationError):
        SwingConfig.model_validate({"shariah": {"provider": "zoya"}})


def test_paper_journal_does_not_write_a_no_trade(tmp_path: Path):
    envelope = analyze("AAPL", config=SwingConfig(), env={}, fetch_market=False)
    assert envelope.decision is DecisionKind.NO_TRADE
    PaperJournal(tmp_path / "journal.jsonl").append(envelope, equity_usd=None)
    assert not (tmp_path / "journal.jsonl").exists()
