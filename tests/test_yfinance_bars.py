"""yfinance bars are split-adjusted, cached, and offline in tests."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from swing.data.yfinance_bars import YFinanceBarProvider, bars_from_yfinance_frames

_NY = ZoneInfo("America/New_York")


def _frames():
    index = pd.to_datetime(["2024-08-29", "2024-08-30", "2024-09-03"]).tz_localize(_NY)
    adjusted = pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0],
            "High": [101.0, 102.0, 103.0],
            "Low": [99.0, 100.0, 101.0],
            "Close": [100.0, 101.0, 102.0],
            "Volume": [1000.0, 1100.0, 1200.0],
            "Dividends": [0.0, 0.0, 0.0],
            "Stock Splits": [0.0, 0.0, 4.0],
        },
        index=index,
    )
    raw = pd.DataFrame(
        {
            "Open": [400.0, 404.0, 102.0],
            "High": [404.0, 408.0, 103.0],
            "Low": [396.0, 400.0, 101.0],
            "Close": [400.0, 404.0, 102.0],
            "Volume": [1000.0, 1100.0, 1200.0],
        },
        index=index,
    )
    return adjusted, raw


def test_frames_become_split_adjusted_bars_with_a_clean_split():
    series = bars_from_yfinance_frames("AAPL", *_frames())
    assert series.provider == "yfinance"
    assert series.adjustment == "split_and_dividend"
    assert series.corp_action_suspect is False
    assert [bar.session.isoformat() for bar in series.bars] == ["2024-08-29", "2024-08-30", "2024-09-03"]
    assert series.bars[0].close == 100.0
    assert series.bars[0].raw_close == 400.0
    assert series.bars[-1].close == 102.0
    assert series.bars[-1].volume == 1200.0


def test_provider_caches_and_does_not_call_the_vendor_twice(tmp_path: Path):
    calls = {"n": 0}

    def download(ticker: str, start, end):
        calls["n"] += 1
        assert ticker == "AAPL"
        return _frames()

    now = datetime(2024, 9, 3, 17, 0, tzinfo=_NY)
    provider = YFinanceBarProvider(download=download, cache_dir=tmp_path, now=lambda: now)
    first = provider.fetch_daily("aapl", 2)
    second = provider.fetch_daily("AAPL", 2)
    assert calls["n"] == 1
    assert len(first.bars) == 2
    assert first.bars[0].session.isoformat() == "2024-08-30"
    assert second.bars[-1].close == first.bars[-1].close
    assert (tmp_path / "AAPL.parquet").is_file()
    assert first.corp_action_suspect is False
