"""Parquet cache stores split-adjusted OHLC and the suspect flag."""

from datetime import date
from pathlib import Path

from swing.data.cache import read_bars, write_bars
from swing.data.models import BarSeries, DailyBar
from swing.paths import bars_cache_dir


def _series() -> BarSeries:
    return BarSeries(
        ticker="AAPL",
        provider="yfinance",
        bars=(
            DailyBar(
                session=date(2024, 8, 29),
                open=10.0,
                high=11.0,
                low=9.5,
                close=10.5,
                volume=1_500.0,
                raw_close=42.0,
            ),
            DailyBar(
                session=date(2024, 8, 30),
                open=10.5,
                high=12.0,
                low=10.0,
                close=11.0,
                volume=1_800.0,
                raw_close=44.0,
            ),
        ),
        corp_action_suspect=True,
        corp_action_reasons=("missing_split",),
        adjustment="split_and_dividend",
    )


def test_roundtrip_keeps_split_adjusted_ohlc_and_suspect_flag(tmp_path: Path):
    write_bars(tmp_path, _series())
    loaded = read_bars(tmp_path, "AAPL")
    assert loaded is not None
    assert loaded.ticker == "AAPL"
    assert loaded.provider == "yfinance"
    assert loaded.adjustment == "split_and_dividend"
    assert loaded.corp_action_suspect is True
    assert loaded.corp_action_reasons == ("missing_split",)
    assert loaded.bars[0].session == date(2024, 8, 29)
    assert loaded.bars[0].open == 10.0
    assert loaded.bars[0].high == 11.0
    assert loaded.bars[0].low == 9.5
    assert loaded.bars[0].close == 10.5
    assert loaded.bars[0].volume == 1_500.0
    assert loaded.bars[0].raw_close == 42.0
    assert loaded.bars[1].close == 11.0


def test_cache_file_is_under_the_macos_bars_cache_dir(tmp_path: Path):
    cache = bars_cache_dir(platform="darwin", home=Path("/Users/ziad"), env={"SWING_DATA_DIR": str(tmp_path)})
    write_bars(cache, _series())
    assert (tmp_path / "cache" / "bars" / "AAPL.parquet").is_file()
    assert cache == tmp_path / "cache" / "bars"


def test_missing_cache_returns_none(tmp_path: Path):
    assert read_bars(tmp_path, "AAPL") is None


def _jump(close_a: float, close_b: float, reason: str) -> BarSeries:
    return BarSeries(
        ticker="CRWV",
        provider="yfinance",
        bars=(
            DailyBar(
                session=date(2025, 3, 31),
                open=close_a,
                high=close_a,
                low=close_a,
                close=close_a,
                volume=1.0,
                raw_close=close_a,
            ),
            DailyBar(
                session=date(2025, 4, 1),
                open=close_b,
                high=close_b,
                low=close_b,
                close=close_b,
                volume=1.0,
                raw_close=close_b,
            ),
        ),
        corp_action_suspect=True,
        corp_action_reasons=(reason,),
        adjustment="split_and_dividend",
    )


def test_stale_unexplained_gap_clears_when_the_jump_is_not_a_split(tmp_path: Path):
    write_bars(tmp_path, _jump(37.08, 52.57, "unexplained_gap"))
    loaded = read_bars(tmp_path, "CRWV")
    assert loaded is not None
    assert loaded.corp_action_suspect is False
    assert loaded.corp_action_reasons == ()


def test_stale_unexplained_gap_stays_when_the_jump_is_a_split(tmp_path: Path):
    write_bars(tmp_path, _jump(100.0, 50.0, "unexplained_gap"))
    loaded = read_bars(tmp_path, "CRWV")
    assert loaded is not None
    assert loaded.corp_action_suspect is True
    assert loaded.corp_action_reasons == ("unexplained_gap",)
