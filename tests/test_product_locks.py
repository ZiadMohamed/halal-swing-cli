"""Cash, long equity only. Shariah codes stay unused on the v0 path."""

from pathlib import Path

import pytest

from swing.analyze import analyze
from swing.broker.ibkr import IbkrBrokerStub
from swing.codes import SHARIAH_REASON_CODES, DecisionKind, ReasonCode
from swing.config import SwingConfig
from swing.guards import product_block
from swing.journal.paper import PaperJournal
from swing.research.models import ResearchResult


def test_there_is_no_enter_short_decision():
    names = set(DecisionKind.__members__) | set(ReasonCode.__members__)
    assert "ENTER_SHORT" not in names
    assert DecisionKind.ENTER_LONG.value == "ENTER_LONG"


def test_product_guard_blocks_short_margin_and_derivatives():
    assert product_block(side="short", instrument="equity", account_mode="cash") is ReasonCode.BLOCK_SHORT
    assert product_block(side="long", instrument="option", account_mode="cash") is ReasonCode.BLOCK_DERIVATIVE
    assert product_block(side="long", instrument="cfd", account_mode="cash") is ReasonCode.BLOCK_DERIVATIVE
    assert product_block(side="long", instrument="future", account_mode="cash") is ReasonCode.BLOCK_DERIVATIVE
    assert product_block(side="long", instrument="equity", account_mode="margin") is ReasonCode.BLOCK_MARGIN
    assert product_block(side="long", instrument="equity", account_mode="cash") is None
    assert product_block(side="long", instrument="futures", account_mode="cash") is ReasonCode.BLOCK_DERIVATIVE
    assert product_block(side="long", instrument="equity", account_mode="cash", longs_only=False) is ReasonCode.BLOCK_SHORT


def test_shariah_codes_are_reserved_on_the_enum():
    assert ReasonCode.BLOCK_SHARIAH_SCREEN in SHARIAH_REASON_CODES
    assert ReasonCode.WARN_PURIFICATION in SHARIAH_REASON_CODES
    assert ReasonCode.BLOCK_SHORT not in SHARIAH_REASON_CODES


def test_ibkr_stub_does_not_trade():
    with pytest.raises(NotImplementedError) as caught:
        IbkrBrokerStub().place_order(object())
    text = str(caught.value).lower()
    assert "live trading" in text
    assert "out of scope" in text


def test_paper_journal_append_records_plans_instead_of_raising(tmp_path: Path):
    envelope = analyze(
        "AAPL",
        config=SwingConfig(),
        env={},
        fetch_market=False,
        research_result=ResearchResult(status="skipped", provider="none", reason="disabled", query=None, hits=()),
    )
    assert envelope.decision is DecisionKind.NO_TRADE
    PaperJournal(tmp_path / "journal.jsonl").append(envelope, equity_usd=None)
    assert not (tmp_path / "journal.jsonl").exists()
