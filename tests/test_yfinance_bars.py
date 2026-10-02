"""yfinance bars: one download, no NaN-to-zero, freshness, rebuild, and a final-only cache."""

from datetime import date, datetime
from pathlib import Path

from swing.data.cache import read_bars, write_bars
from swing.data.models import BarSeries, DailyBar
from swing.data.yfinance_bars import YFinanceBarProvider
from tests.fake_yahoo import NAN, NY, FakeYahoo, daily_frame, hourly_frame, steady_rows

SESSIONS = ["2026-09-24", "2026-09-25", "2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01"]
# 2026-10-02 01:00 New York is 08:00 in Cairo: the morning decision window.
CAIRO_MORNING = datetime(2026, 10, 2, 1, 0, tzinfo=NY)


def _provider(tmp_path: Path, client: FakeYahoo, now: datetime) -> YFinanceBarProvider:
    return YFinanceBarProvider(cache_dir=tmp_path, client=client, now=lambda: now)


def _nan_tail_frame():
    rows = steady_rows(SESSIONS[:-1])
    rows.append(("2026-10-01", NAN, NAN, NAN, NAN, 36_000_000.0))
    return daily_frame(rows)


def test_one_history_call_and_a_clean_split_is_not_suspect(tmp_path: Path):
    rows = [
        ("2024-08-29", 100.0, 101.0, 99.0, 100.0, 1000.0),
        ("2024-08-30", 101.0, 102.0, 100.0, 101.0, 1100.0),
        ("2024-09-03", 102.0, 103.0, 101.0, 102.0, 1200.0),
    ]
    client = FakeYahoo(daily=daily_frame(rows, splits={"2024-09-03": 4.0}))
    series = _provider(tmp_path, client, datetime(2024, 9, 3, 18, 0, tzinfo=NY)).fetch_daily("aapl", 3)
    assert client.count("daily") == 1
    assert series.provider == "yfinance"
    assert series.adjustment == "split_and_dividend"
    assert series.corp_action_suspect is False
    assert [bar.session.isoformat() for bar in series.bars] == ["2024-08-29", "2024-08-30", "2024-09-03"]
    assert series.bars[-1].close == 102.0
    assert series.bars[-1].volume == 1200.0


def test_cached_final_bars_are_not_downloaded_twice(tmp_path: Path):
    client = FakeYahoo(daily=daily_frame(steady_rows(SESSIONS)))
    provider = _provider(tmp_path, client, CAIRO_MORNING)
    first = provider.fetch_daily("AAPL", 3)
    second = provider.fetch_daily("AAPL", 3)
    assert client.count("daily") == 1
    assert first.bars[-1].session == date(2026, 10, 1)
    assert second.bars == first.bars
    assert (tmp_path / "AAPL.parquet").is_file()


def test_nan_tail_is_dropped_rebuilt_from_hourly_bars_and_never_cached(tmp_path: Path):
    client = FakeYahoo(daily=_nan_tail_frame(), hourly=hourly_frame("2026-10-01", first=200.0))
    provider = _provider(tmp_path, client, CAIRO_MORNING)
    series = provider.fetch_daily("AAPL", 3)
    last = series.bars[-1]
    assert series.reconstructed is True
    assert last.session == date(2026, 10, 1)
    assert last.open == 200.0
    assert last.high == 208.0
    assert last.low == 199.0
    assert last.close == 206.5
    assert last.volume == 36_000_000.0
    assert all(bar.close > 0 and bar.open > 0 for bar in series.bars)

    cached = read_bars(tmp_path, "AAPL")
    assert cached is not None
    assert cached.bars[-1].session == date(2026, 9, 30)
    assert all(bar.close > 0 for bar in cached.bars)

    provider.fetch_daily("AAPL", 3)
    assert client.count("daily") == 2


def test_nan_tail_without_usable_hourly_bars_stays_stale(tmp_path: Path):
    partial_hours = hourly_frame("2026-10-01", count=4)
    for hourly in (None, RuntimeError("rate limited"), partial_hours):
        client = FakeYahoo(daily=_nan_tail_frame(), hourly=hourly)
        series = _provider(tmp_path / str(id(client)), client, CAIRO_MORNING).fetch_daily("AAPL", 3)
        assert series.reconstructed is False
        assert series.bars[-1].session == date(2026, 9, 30)
        assert all(bar.close > 0 for bar in series.bars)


def test_rebuild_keeps_hourly_volume_only_when_the_daily_row_is_absent(tmp_path: Path):
    client = FakeYahoo(daily=daily_frame(steady_rows(SESSIONS[:-1])), hourly=hourly_frame("2026-10-01"))
    series = _provider(tmp_path, client, CAIRO_MORNING).fetch_daily("AAPL", 3)
    assert series.reconstructed is True
    assert series.bars[-1].volume == 700_000.0


def test_partial_intraday_bar_is_ignored_and_not_cached(tmp_path: Path):
    during_session = datetime(2026, 10, 1, 12, 0, tzinfo=NY)
    client = FakeYahoo(daily=daily_frame(steady_rows(SESSIONS)))
    series = _provider(tmp_path, client, during_session).fetch_daily("AAPL", 3)
    assert series.bars[-1].session == date(2026, 9, 30)
    assert series.reconstructed is False
    assert client.count("hourly") == 0
    cached = read_bars(tmp_path, "AAPL")
    assert cached is not None and cached.bars[-1].session == date(2026, 9, 30)


def test_a_bar_minutes_after_the_close_is_used_but_not_cached_until_it_settles(tmp_path: Path):
    after_bell = datetime(2026, 10, 1, 16, 10, tzinfo=NY)
    client = FakeYahoo(daily=daily_frame(steady_rows(SESSIONS)))
    series = _provider(tmp_path, client, after_bell).fetch_daily("AAPL", 3)
    assert series.bars[-1].session == date(2026, 10, 1)
    cached = read_bars(tmp_path, "AAPL")
    assert cached is not None and cached.bars[-1].session == date(2026, 9, 30)


def test_a_zero_or_nan_row_mid_series_is_dropped_not_coerced(tmp_path: Path):
    rows = steady_rows(SESSIONS)
    rows[2] = (rows[2][0], 0.0, 0.0, 0.0, 0.0, 5.0)
    rows[3] = (rows[3][0], 101.0, NAN, 99.0, 100.0, 5.0)
    client = FakeYahoo(daily=daily_frame(rows))
    series = _provider(tmp_path, client, CAIRO_MORNING).fetch_daily("AAPL", 10)
    sessions = [bar.session.isoformat() for bar in series.bars]
    assert "2026-09-28" not in sessions
    assert "2026-09-29" not in sessions
    assert all(bar.low > 0 and bar.high > 0 for bar in series.bars)


def test_instrument_type_comes_from_history_metadata_and_survives_the_cache(tmp_path: Path):
    client = FakeYahoo(daily=daily_frame(steady_rows(SESSIONS)), meta={"instrumentType": "ETF"})
    provider = _provider(tmp_path, client, CAIRO_MORNING)
    assert provider.fetch_daily("SPUS", 3).instrument_type == "ETF"
    assert provider.fetch_daily("SPUS", 3).instrument_type == "ETF"
    assert client.count("daily") == 1


def test_a_cache_written_with_zero_prices_is_cleaned_on_read(tmp_path: Path):
    good = DailyBar(date(2026, 9, 30), 10.0, 11.0, 9.0, 10.5, 100.0, 10.5)
    zero = DailyBar(date(2026, 10, 1), 0.0, 0.0, 0.0, 0.0, 100.0, 0.0)
    path = tmp_path / "AAPL.parquet"
    write_bars(tmp_path, BarSeries("AAPL", "yfinance", (good,), False, (), "split_and_dividend"))
    import pyarrow.parquet as pq

    table = pq.read_table(path)
    rows = table.to_pylist() + [
        {"session": zero.session, "open": 0.0, "high": 0.0, "low": 0.0, "close": 0.0, "volume": 100.0, "raw_close": 0.0}
    ]
    import pyarrow as pa

    pq.write_table(pa.Table.from_pylist(rows, schema=table.schema), path)
    loaded = read_bars(tmp_path, "AAPL")
    assert loaded is not None
    assert [bar.session for bar in loaded.bars] == [date(2026, 9, 30)]
