"""Append-only paper JSONL. One planned ENTER_LONG per line. No network."""

import json
from pathlib import Path

import pytest

from swing.brain.positions import OpenPosition
from swing.journal.paper import PaperJournal
from tests.synthetic import enter_envelope, no_trade_envelope

EQUITY = 100_000.0


def test_enter_long_appends_one_json_object_and_copies_size(tmp_path: Path):
    path = tmp_path / "nested" / "journal.jsonl"
    journal = PaperJournal(path)
    envelope = enter_envelope(size_shares=20, entry=100.0, stop=95.0)
    journal.append(envelope, equity_usd=EQUITY, sector="tech")

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["ticker"] == "AAPL"
    assert record["decision"] == "ENTER_LONG"
    assert record["size_shares"] == 20
    assert record["entry"] == 100.0
    assert record["stop"] == 95.0
    assert record["sector"] == "tech"
    assert record["equity_usd"] == EQUITY
    # floor(100_000 * 0.01 / 5) would be 200 shares. The journal must copy 20.
    assert record["size_shares"] != 200
    assert record["risk_fraction"] == pytest.approx(20 * (100.0 - 95.0) / EQUITY)
    positions = journal.load_positions()
    assert len(positions) == 1
    assert positions[0].ticker == "AAPL"
    assert positions[0].sector == "tech"
    assert positions[0].risk_fraction == pytest.approx(record["risk_fraction"])


def test_second_enter_appends_and_does_not_rewrite_the_first_line(tmp_path: Path):
    journal = PaperJournal(tmp_path / "journal.jsonl")
    journal.append(enter_envelope(ticker="MSFT", size_shares=20), equity_usd=EQUITY, sector=None)
    first = journal.path.read_bytes()
    journal.append(enter_envelope(ticker="NVDA", size_shares=10), equity_usd=EQUITY, sector="chips")
    body = journal.path.read_bytes()
    assert body.startswith(first)
    assert first.endswith(b"\n")
    lines = body.decode("utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["ticker"] == "MSFT"
    assert json.loads(lines[1])["ticker"] == "NVDA"
    assert json.loads(lines[1])["risk_fraction"] == pytest.approx(10 * 5 / EQUITY)
    loaded = journal.load_positions()
    assert [item.ticker for item in loaded] == ["MSFT", "NVDA"]
    assert loaded[1] == OpenPosition(ticker="NVDA", risk_fraction=loaded[1].risk_fraction, sector="chips")


def test_no_trade_does_not_create_or_rewrite_the_file(tmp_path: Path):
    journal = PaperJournal(tmp_path / "journal.jsonl")
    journal.append(no_trade_envelope(), equity_usd=None)
    journal.append(no_trade_envelope(), equity_usd=EQUITY)
    assert not journal.path.exists()

    journal.append(enter_envelope(), equity_usd=EQUITY)
    before = journal.path.read_bytes()
    journal.append(no_trade_envelope(), equity_usd=None)
    assert journal.path.read_bytes() == before


def test_unset_or_non_positive_equity_does_not_invent_a_fraction(tmp_path: Path):
    journal = PaperJournal(tmp_path / "journal.jsonl")
    envelope = enter_envelope()
    for equity in (None, 0, -1):
        with pytest.raises(ValueError, match="equity"):
            journal.append(envelope, equity_usd=equity)
    assert not journal.path.exists()


def test_missing_journal_loads_an_empty_book(tmp_path: Path):
    assert PaperJournal(tmp_path / "missing.jsonl").load_positions() == ()


def test_blank_sector_is_not_a_bucket_and_a_bad_line_fails_closed(tmp_path: Path):
    path = tmp_path / "journal.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ticker": "MSFT",
                        "decision": "ENTER_LONG",
                        "risk_fraction": 0.02,
                        "sector": "  ",
                    }
                ),
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    loaded = PaperJournal(path).load_positions()
    assert loaded == (OpenPosition(ticker="MSFT", risk_fraction=0.02, sector=None),)

    path.write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="journal"):
        PaperJournal(path).load_positions()


def test_a_line_without_risk_fraction_is_not_treated_as_zero(tmp_path: Path):
    path = tmp_path / "journal.jsonl"
    path.write_text(json.dumps({"ticker": "MSFT", "decision": "ENTER_LONG"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="risk_fraction"):
        PaperJournal(path).load_positions()
