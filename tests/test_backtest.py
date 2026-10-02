"""Backtest mechanics on synthetic bars. No network and no parameter search."""

from datetime import date, timedelta

from swing.backtest import VARIANTS, candidates_on, run_backtest, scan_day
from swing.brain.rules import SignalTape, candidate_for
from swing.brain.portfolio import scan_allocations
from swing.brain.rules import Candidate, Variant
from swing.config import SwingConfig
from swing.data.calendar import NyseCalendar
from swing.data.models import DailyBar

START = date(2024, 6, 3)


def _sessions(count: int, end: date | None = None) -> list[date]:
    calendar = NyseCalendar()
    cursor = end or date(2024, 10, 1)
    found: list[date] = []
    while len(found) < count:
        if calendar.is_session(cursor):
            found.append(cursor)
        cursor -= timedelta(days=1)
    return list(reversed(found))


def _bars(sessions: list[date], closes: list[float], *, volume: float = 1_000_000.0, last_volume: float | None = None) -> tuple[DailyBar, ...]:
    bars: list[DailyBar] = []
    for index, (session, close) in enumerate(zip(sessions, closes)):
        vol = last_volume if last_volume is not None and index == len(sessions) - 1 else volume
        bars.append(
            DailyBar(
                session=session,
                open=close,
                high=close + 0.4,
                low=close - 0.4,
                close=close,
                volume=vol,
                raw_close=close,
            )
        )
    return tuple(bars)


def _breakout(sessions: list[date]) -> tuple[DailyBar, ...]:
    closes = [100 + index * 0.05 for index in range(len(sessions))]
    prior = max(close + 0.4 for close in closes[-21:-1])
    closes[-1] = prior + 1
    bars = list(_bars(sessions, closes, last_volume=3_000_000.0))
    last = closes[-1]
    bars[-1] = DailyBar(sessions[-1], last, last + 0.2, last - 0.2, last, 3_000_000.0, last)
    return tuple(bars)


def _variant(**changes) -> Variant:
    base = dict(
        name="t",
        triggers=("BO_RVOL",),
        rank="random",
        seed=1,
        exit="target_2r",
        slots=4,
        max_position_frac=None,
        risk=0.01,
        regime=False,
        earnings="off",
        entry_cap_atr=None,
    )
    base.update(changes)
    return Variant(**base)


def test_prepared_tape_matches_the_shared_signal():
    sessions = _sessions(80)
    bars = _breakout(sessions)
    config = SwingConfig()
    variant = _variant()
    calendar = NyseCalendar()
    tape = SignalTape(bars, config)
    for index in (40, 60, 79):
        prefix = bars[: index + 1]
        slow = candidate_for("AAA", prefix, config=config, variant=variant, calendar=calendar)
        fast = tape.candidate(prefix[-1].session, "AAA", variant, calendar)
        assert fast == slow


def test_scan_day_matches_candidates_on_a_fixture_day():
    sessions = _sessions(80)
    panels = {"AAA": _breakout(sessions)}
    kwargs = dict(
        variant=_variant(),
        config=SwingConfig(),
        calendar=NyseCalendar(),
        earnings={},
        spy=None,
        held=set(),
    )
    assert scan_day(panels, sessions[-1], **kwargs) == candidates_on(panels, sessions[-1], **kwargs)
    assert scan_day(panels, sessions[-1], **kwargs)[0].triggers == ("BO_RVOL",)


def test_gap_through_stop_fills_at_the_open_and_cash_settles_next_session():
    sessions = _sessions(90)
    signal = sessions[79]
    entry = sessions[80]
    sale = sessions[81]
    later = sessions[83]
    first = list(_breakout(sessions[:80]))
    # Hold a flat day, then gap through the stop, then recover so a second name can be bought only after settlement.
    first.append(DailyBar(entry, first[-1].close, first[-1].close + 0.2, first[-1].close - 0.2, first[-1].close, 1_000_000, first[-1].close))
    stop_open = 1.0
    first.append(DailyBar(sale, stop_open, stop_open + 0.1, stop_open, stop_open, 1_000_000, stop_open))
    for session in sessions[82:]:
        first.append(DailyBar(session, 50, 50.2, 49.8, 50, 1_000_000, 50))
    second_sessions = sessions[:84]
    second = list(_breakout(second_sessions))
    # Keep the second name signalling on the sale day and the day after.
    last_close = second[-1].close
    for session in sessions[84:]:
        second.append(DailyBar(session, last_close, last_close + 0.2, last_close - 0.2, last_close, 3_000_000, last_close))
    panels = {"AAA": tuple(first), "BBB": tuple(second)}
    variant = _variant(risk=1.0)
    result = run_backtest(
        panels,
        variant=variant,
        start=sessions[0],
        end=sessions[-1],
        calendar=NyseCalendar(),
    )
    aaa = [trade for trade in result.trades if trade.ticker == "AAA"]
    assert aaa and aaa[0].exit_session == sale
    assert aaa[0].exit == stop_open
    assert aaa[0].reason == "stop"
    bbb = [trade for trade in result.trades if trade.ticker == "BBB"]
    if bbb:
        assert bbb[0].entry_session >= later


def test_entry_cap_skips_a_gap_above_the_cap():
    sessions = _sessions(82)
    bars = list(_breakout(sessions[:80]))
    close = bars[-1].close
    bars.append(DailyBar(sessions[80], close + 50, close + 51, close + 49, close + 50, 1_000_000, close + 50))
    bars.append(DailyBar(sessions[81], close, close, close, close, 1_000_000, close))
    capped = run_backtest(
        {"AAA": tuple(bars)},
        variant=_variant(entry_cap_atr=0.25),
        start=sessions[0],
        end=sessions[-1],
    )
    opened = run_backtest(
        {"AAA": tuple(bars)},
        variant=_variant(entry_cap_atr=None),
        start=sessions[0],
        end=sessions[-1],
    )
    assert capped.metrics.trades == 0
    assert opened.metrics.trades >= 1


def test_same_inputs_are_identical_and_momentum_ranks_above_random_cash_cap():
    left = Candidate("AAA", date(2024, 6, 3), ("BO_RVOL",), 10, 2, 0.5, None)
    right = Candidate("BBB", date(2024, 6, 3), ("BO_RVOL",), 10, 2, 0.1, None)
    variant = _variant(rank="momentum", max_position_frac=0.20, risk=0.5)
    rng = __import__("random").Random(1)
    first = scan_allocations([right, left], variant=variant, free_slots=1, settled_cash=50, equity=100, rng=rng)
    second = scan_allocations([right, left], variant=variant, free_slots=1, settled_cash=50, equity=100, rng=__import__("random").Random(1))
    assert first == second
    assert first[0].candidate.ticker == "AAA"
    assert first[0].shares * 10 <= 50


def test_registered_variants_are_the_appendix_list_only():
    assert set(VARIANTS) == {
        "A",
        "B",
        "C",
        "M",
        "D2",
        "I",
        "J",
        "K",
        "L",
        "H",
        "E",
        "G",
        "I_moo",
        "I_cap",
        "v1",
        "v1_random",
    }
    assert VARIANTS["D2"].exit == "trail"
    assert VARIANTS["M"].exit == "target_2r"
    assert VARIANTS["I"].slots == 5
    assert VARIANTS["J"].rank == "random"
    assert VARIANTS["H"].entry_cap_atr == 0.25
    assert VARIANTS["E"].earnings == "through"
    assert VARIANTS["C"].earnings == "exit"


def test_backtest_command_does_not_download(capsys):
    from swing.cli import main

    assert main(["backtest", "--variant", "D2"]) == 2
    assert "does not download" in capsys.readouterr().err
