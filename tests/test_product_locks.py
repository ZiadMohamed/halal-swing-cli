"""Cash, long equity only. Shariah codes stay unused on the v0 path."""

from swing.broker.ibkr import IbkrBrokerStub
from swing.codes import SHARIAH_REASON_CODES, DecisionKind, ReasonCode
from swing.guards import product_block
from swing.journal.paper import PaperJournal


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


def test_shariah_codes_are_reserved_on_the_enum():
    assert ReasonCode.BLOCK_SHARIAH_SCREEN in SHARIAH_REASON_CODES
    assert ReasonCode.WARN_PURIFICATION in SHARIAH_REASON_CODES
    assert ReasonCode.BLOCK_SHORT not in SHARIAH_REASON_CODES


def test_ibkr_stub_does_not_trade():
    with pytest_raises_not_implemented():
        IbkrBrokerStub().place_order(object())


def test_paper_journal_is_not_wired_yet():
    with pytest_raises_not_implemented():
        PaperJournal().append(object())


class pytest_raises_not_implemented:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            raise AssertionError("expected NotImplementedError")
        if not issubclass(exc_type, NotImplementedError):
            return False
        text = str(exc).lower()
        assert "v0" in text or "out of scope" in text or "not installed" in text or "hardening" in text
        return True
