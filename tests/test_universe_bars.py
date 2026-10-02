"""Grouped daily updates the universe. Backfill stays inside five calls a minute."""

from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from swing.data.cache import write_bars
from swing.data.massive import MassiveBarProvider, parse_grouped_daily
from swing.data.models import BarSeries, DailyBar
from swing.data.throttle import RateLimiter

_NY = ZoneInfo("America/New_York")
NOW = datetime(2024, 9, 3, 18, 0, tzinfo=_NY)
LAST = date(2024, 9, 3)


def _limiter():
    clock = {"t": 0.0}

    def now() -> float:
        return clock["t"]

    def sleep(seconds: float) -> None:
        clock["t"] += seconds

    return RateLimiter(5, now=now, sleep=sleep), clock


def _bars(end: date, count: int, close: float = 100.0) -> tuple[DailyBar, ...]:
    found: list[DailyBar] = []
    cursor = end
    while len(found) < count:
        if cursor.weekday() < 5:
            price = close + len(found)
            found.append(
                DailyBar(session=cursor, open=price, high=price, low=price, close=price, volume=1_000.0, raw_close=price)
            )
        cursor -= timedelta(days=1)
    return tuple(reversed(found))


def _seed(cache: Path, symbols: list[str], end: date, count: int) -> None:
    for symbol in symbols:
        write_bars(
            cache,
            BarSeries(symbol, "massive", _bars(end, count), False, (), "split"),
        )
    (cache / "splits.json").write_text('{"day": "2024-09-03", "splits": {}}', encoding="utf-8")


def test_grouped_daily_parses_tickers_and_drops_a_bad_price():
    payload = {
        "status": "OK",
        "results": [
            {"T": "AAPL", "o": 10, "h": 11, "l": 9, "c": 10.5, "v": 100},
            {"T": "MSFT", "o": float("nan"), "h": 1, "l": 1, "c": 1, "v": 1},
        ],
    }
    bars = parse_grouped_daily(payload, LAST)
    assert list(bars) == ["AAPL"]
    assert bars["AAPL"].close == 10.5
    assert bars["AAPL"].session == LAST


def test_cold_backfill_of_thirty_tickers_stays_inside_the_throttle(tmp_path: Path):
    calls: list[str] = []

    def transport(url: str, headers: dict[str, str]):
        calls.append(url)
        assert "test-key" not in url
        if "/v2/aggs/ticker/" in url and "adjusted=true" in url:
            return {
                "status": "OK",
                "results": [
                    {"o": 100, "h": 101, "l": 99, "c": 100, "v": 10, "t": 1724904000000},
                    {"o": 102, "h": 103, "l": 101, "c": 102, "v": 10, "t": 1725336000000},
                ],
            }
        if "/stocks/v1/splits" in url:
            return {"status": "OK", "results": []}
        raise AssertionError(url)

    limiter, clock = _limiter()
    notes: list[str] = []
    symbols = [f"T{index:02d}" for index in range(30)]
    provider = MassiveBarProvider(
        api_key="test-key",
        cache_dir=tmp_path,
        transport=transport,
        now=lambda: NOW,
        limiter=limiter,
        progress=notes.append,
    )
    loaded = provider.load_universe(symbols, 2)
    assert set(loaded) == set(symbols)
    assert sum("/v2/aggs/ticker/" in url for url in calls) == 30
    assert sum("/stocks/v1/splits" in url for url in calls) == 1
    assert not any("adjusted=false" in url or "/dividends" in url for url in calls)
    assert notes[0] == "backfill 1/30 T00"
    assert notes[-1] == "backfill 30/30 T29"
    assert clock["t"] == 30 * 12.0


def test_warm_universe_makes_no_http_call_and_one_missing_session_is_one_grouped_call(tmp_path: Path):
    symbols = [f"T{index:02d}" for index in range(30)]
    calls: list[str] = []

    def transport(url: str, headers: dict[str, str]):
        calls.append(url)
        assert "/v2/aggs/grouped/" in url
        return {
            "status": "OK",
            "results": [
                {"T": symbol, "o": 110, "h": 111, "l": 109, "c": 110.5, "v": 10} for symbol in symbols
            ],
        }

    provider = MassiveBarProvider(
        api_key="test-key",
        cache_dir=tmp_path,
        transport=transport,
        now=lambda: NOW,
        limiter=RateLimiter(5, sleep=lambda _seconds: (_ for _ in ()).throw(AssertionError("warm call slept"))),
    )
    _seed(tmp_path, symbols, LAST, 5)
    warm = provider.load_universe(symbols, 5)
    assert calls == []
    assert warm["T00"].bars[-1].session == LAST

    for path in tmp_path.glob("*.parquet"):
        path.unlink()
    _seed(tmp_path, symbols, date(2024, 8, 30), 5)
    updated = provider.load_universe(symbols, 5)
    assert len(calls) == 1
    assert "/v2/aggs/grouped/locale/us/market/stocks/2024-09-03" in calls[0]
    assert updated["T00"].bars[-1].session == LAST
    assert updated["T29"].bars[-1].close == 110.5
