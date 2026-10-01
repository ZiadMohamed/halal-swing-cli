"""Split-adjusted bars carry a corp_action_suspect flag Chat 3 can refuse."""

from datetime import date

from swing.data.corp_actions import assess_corp_actions
from swing.data.models import CorporateAction, DailyBar


def _bar(session: str, close: float, raw: float) -> DailyBar:
    return DailyBar(
        session=date.fromisoformat(session),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1_000.0,
        raw_close=raw,
    )


def _split(session: str, new: float = 4.0, old: float = 1.0) -> CorporateAction:
    return CorporateAction(session=date.fromisoformat(session), kind="split", split_to=new, split_from=old)


def _dividend(session: str, amount: float) -> CorporateAction:
    return CorporateAction(session=date.fromisoformat(session), kind="dividend", amount=amount)


def test_quiet_series_is_not_suspect():
    bars = (
        _bar("2024-08-29", 100, 100),
        _bar("2024-08-30", 101, 101),
        _bar("2024-09-03", 102, 102),
    )
    result = assess_corp_actions(bars, (), adjustment="split")
    assert result.suspect is False
    assert result.reasons == ()


def test_recorded_split_with_continuous_adjusted_series_is_clean():
    bars = (
        _bar("2024-08-29", 100, 400),
        _bar("2024-08-30", 101, 404),
        _bar("2024-09-03", 102, 102),
    )
    result = assess_corp_actions(bars, (_split("2024-09-03"),), adjustment="split")
    assert result.suspect is False
    assert result.reasons == ()


def test_silent_split_adjustment_without_a_listed_split_is_missing_split():
    bars = (
        _bar("2024-08-29", 100, 400),
        _bar("2024-08-30", 101, 404),
        _bar("2024-09-03", 102, 102),
    )
    result = assess_corp_actions(bars, (), adjustment="split")
    assert result.suspect is True
    assert "missing_split" in result.reasons


def test_split_sized_gap_in_both_series_without_an_action_is_missing_split():
    bars = (
        _bar("2024-08-29", 400, 400),
        _bar("2024-08-30", 100, 100),
    )
    result = assess_corp_actions(bars, (), adjustment="split_and_dividend")
    assert result.suspect is True
    assert "missing_split" in result.reasons


def test_listed_split_that_leaves_the_adjusted_gap_is_a_mismatch():
    bars = (
        _bar("2024-08-29", 400, 400),
        _bar("2024-08-30", 100, 100),
    )
    result = assess_corp_actions(bars, (_split("2024-08-30"),), adjustment="split")
    assert result.suspect is True
    assert "adjustment_mismatch" in result.reasons


def test_large_move_that_is_not_a_split_ratio_is_an_unexplained_gap():
    bars = (
        _bar("2024-08-29", 100, 100),
        _bar("2024-08-30", 55, 55),
    )
    result = assess_corp_actions(bars, (), adjustment="split")
    assert result.suspect is True
    assert result.reasons == ("unexplained_gap",)


def test_earnings_sized_gap_below_the_split_threshold_is_clean():
    bars = (
        _bar("2024-08-29", 100, 100),
        _bar("2024-08-30", 61, 61),
    )
    result = assess_corp_actions(bars, (), adjustment="split")
    assert result.suspect is False


def test_split_only_series_treats_a_cash_dividend_gap_as_explained():
    bars = (
        _bar("2024-08-29", 100, 100),
        _bar("2024-08-30", 60, 60),
    )
    result = assess_corp_actions(bars, (_dividend("2024-08-30", 40.0),), adjustment="split")
    assert result.suspect is False


def test_dividend_adjusted_series_flags_a_dividend_that_was_not_removed():
    bars = (
        _bar("2024-08-29", 100, 100),
        _bar("2024-08-30", 95, 95),
    )
    result = assess_corp_actions(
        bars,
        (_dividend("2024-08-30", 5.0),),
        adjustment="split_and_dividend",
    )
    assert result.suspect is True
    assert "adjustment_mismatch" in result.reasons


def test_dividend_adjusted_series_accepts_a_removed_dividend():
    bars = (
        _bar("2024-08-29", 100, 100),
        _bar("2024-08-30", 100.5, 95),
    )
    result = assess_corp_actions(
        bars,
        (_dividend("2024-08-30", 5.0),),
        adjustment="split_and_dividend",
    )
    assert result.suspect is False
