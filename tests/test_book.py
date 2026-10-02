"""Fills are append-only. Plans dedupe. Cash and review use a hand fixture."""

from datetime import date
from pathlib import Path

from swing.book import (
    append_buy,
    append_plan,
    append_sell,
    available_cash,
    block_if_open,
    closed_trades,
    import_v0_journal,
    load_book,
    review_summary,
    satellite_vs_benchmark,
    score_plan,
)
from swing.data.models import DailyBar


def _bar(session: str, open_: float, high: float, low: float, close: float) -> DailyBar:
    return DailyBar(date.fromisoformat(session), open_, high, low, close, 1_000.0, close)


def test_book_appends_and_a_bad_line_names_itself(tmp_path: Path):
    path = tmp_path / "book.jsonl"
    append_buy(path, ticker="aapl", shares=10, price=100, day=date(2026, 10, 1), stop=90)
    first = path.read_bytes()
    append_buy(path, ticker="msft", shares=2, price=50, day=date(2026, 10, 1), stop=40)
    assert path.read_bytes().startswith(first)
    _events, lots = load_book(path)
    assert {lot.ticker for lot in lots} == {"AAPL", "MSFT"}
    path.write_bytes(first + b"{not json}\n")
    try:
        load_book(path)
    except ValueError as exc:
        assert "book line 2" in str(exc)
    else:
        raise AssertionError("malformed line was accepted")


def test_available_cash_subtracts_basis_and_same_day_sales(tmp_path: Path):
    path = tmp_path / "book.jsonl"
    append_buy(path, ticker="AAPL", shares=10, price=100, day=date(2026, 10, 1), stop=90)
    append_sell(path, ticker="AAPL", shares=4, price=110, day=date(2026, 10, 2), reason="manual")
    events, lots = load_book(path)
    assert sum(lot.shares for lot in lots) == 6
    # equity 10_000, remaining basis 6*100, same-day sale 4*110.
    assert available_cash(10_000, lots, events, date(2026, 10, 2)) == 10_000 - 600 - 440
    assert available_cash(10_000, lots, events, date(2026, 10, 3)) == 10_000 - 600


def test_open_ticker_is_not_planned_twice(tmp_path: Path):
    book = tmp_path / "book.jsonl"
    plans = tmp_path / "plans.jsonl"
    append_buy(book, ticker="AAPL", shares=1, price=10, day=date(2026, 10, 1), stop=9)
    _events, lots = load_book(book)
    assert block_if_open("AAPL", lots) is True
    assert block_if_open("MSFT", lots) is False
    record = {"ticker": "MSFT", "signal_session": "2026-10-01", "config_hash": "ab" * 32, "entry": 10, "stop": 9}
    assert append_plan(plans, record) is True
    assert append_plan(plans, record) is False
    assert len(plans.read_text(encoding="utf-8").splitlines()) == 1


def test_review_math_matches_a_hand_trade_and_stays_unproven():
    trades = closed_trades_from_numbers()
    summary = review_summary(trades)
    # entry 100, stop 90, exit 120. R = 2. One trade, so unproven.
    assert trades[0]["r"] == 2
    assert summary["n"] == 1
    assert summary["mean_r"] == 2
    assert summary["label"] == "unproven"
    assert summary["win_rate"] == 1
    many = [{"r": 1.0, "hold_days": 4} for _ in range(100)]
    proven = review_summary(many)
    assert proven["label"] == "proven"
    assert proven["mean_r"] == 1
    losers = [{"r": -0.2, "hold_days": 1} for _ in range(100)]
    assert review_summary(losers)["label"] == "unproven"


def test_satellite_return_matches_the_hand_worked_benchmark():
    trades = closed_trades_from_numbers()
    bars = (
        _bar("2026-10-01", 100, 101, 99, 100),
        _bar("2026-10-08", 110, 111, 109, 110),
    )
    satellite, benchmark = satellite_vs_benchmark(trades, bars)
    assert abs(satellite - 0.2) < 1e-9
    assert abs(benchmark - 0.1) < 1e-9


def test_forward_score_is_the_hand_worked_two_r():
    bars = (
        _bar("2026-10-01", 99, 100, 98, 100),
        _bar("2026-10-02", 100, 101, 97, 100.5),
        _bar("2026-10-05", 101, 121, 100, 120),
    )
    plan = {"signal_session": "2026-10-01", "stop": 90, "target": 120}
    assert score_plan(plan, bars) == 2


def test_v0_journal_is_copied_and_imported_as_plans_only(tmp_path: Path):
    journal = tmp_path / "journal.jsonl"
    journal.write_text(
        '{"config_hash":"ab","decision":"ENTER_LONG","entry":10,"next_open":"2026-10-02T09:30:00-04:00",'
        '"stop":9,"target":12,"ticker":"AAPL","size_shares":5}\n',
        encoding="utf-8",
    )
    added = import_v0_journal(journal, tmp_path / "plans.jsonl", tmp_path / "journal.v0.jsonl")
    assert added == 1
    assert journal.is_file()
    assert (tmp_path / "journal.v0.jsonl").read_bytes() == journal.read_bytes()
    _events, lots = load_book(tmp_path / "book.jsonl")
    assert lots == []
    again = import_v0_journal(journal, tmp_path / "plans.jsonl", tmp_path / "journal.v0.jsonl")
    assert again == 0


def test_cli_buy_sell_and_review_are_append_only(tmp_path: Path, monkeypatch, capsys):
    from swing.cli import main

    monkeypatch.setenv("SWING_HOME", str(tmp_path))
    monkeypatch.delenv("SWING_DATA_DIR", raising=False)
    assert main(["buy", "AAPL", "--shares", "10", "--price", "100", "--stop", "90", "--date", "2026-10-01"]) == 0
    assert main(["sell", "AAPL", "--shares", "10", "--price", "120", "--date", "2026-10-08"]) == 0
    assert main(["sell", "AAPL", "--shares", "1", "--price", "120", "--date", "2026-10-09"]) == 2
    code = main(["review"])
    assert code == 0
    text = capsys.readouterr().out
    assert "mean R 2.000" in text
    assert "unproven" in text
    assert "did not send" in text


def closed_trades_from_numbers():
    from swing.book import Buy, Sell

    events = [
        Buy("AAPL", 10, 100.0, date(2026, 10, 1), 90.0, None, None, None, None, 1),
        Sell("AAPL", 10, 120.0, date(2026, 10, 8), "manual", 2),
    ]
    return closed_trades(events)
