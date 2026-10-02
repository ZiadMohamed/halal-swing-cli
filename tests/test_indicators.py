"""Indicator formulas on split-adjusted closes. No network."""

import pytest

from swing.brain.indicators import atr, ema, rsi, sma


def test_sma_uses_the_last_window_only():
    assert sma((1, 2, 3, 4, 5), 3) == pytest.approx(4)


def test_sma_is_none_without_a_full_window():
    assert sma((1, 2), 3) is None


def test_ema_seeds_with_the_sma_then_smooths():
    # Period 3. Seed (1+2+3)/3 = 2. k = 0.5.
    # 4 → 3, 5 → 4.
    assert ema((1, 2, 3, 4, 5), 3) == pytest.approx(4)


def test_wilder_rsi_matches_the_hand_worked_series():
    # Deltas +1, +1, -1, -1. Seed avg gain 1, avg loss 0.
    # After the two down closes the latest RSI is 25.
    assert rsi((10, 11, 12, 11, 10), 2) == pytest.approx(25)


def test_rsi_is_100_when_nothing_has_fallen():
    assert rsi((10, 11, 12), 2) == pytest.approx(100)


def test_wilder_atr_smooths_true_range():
    highs = (10, 11, 10)
    lows = (8, 10, 7)
    closes = (9, 10.5, 8)
    # TRs: 2, 2, 3.5. Seed ATR (2+2)/2 = 2. Next (2 + 3.5) / 2 = 2.75.
    assert atr(highs, lows, closes, 2) == pytest.approx(2.75)


def test_indicators_do_not_read_a_raw_close_argument():
    # The public functions take adjusted prices only. There is no raw_close parameter.
    assert "raw_close" not in sma.__code__.co_varnames
    assert "raw_close" not in rsi.__code__.co_varnames
    assert "raw_close" not in atr.__code__.co_varnames
