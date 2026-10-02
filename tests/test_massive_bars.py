"""Massive Basic daily bars. The API key stays out of URLs and errors."""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from swing.config import SwingConfig
from swing.data.errors import MissingApiKeyError
from swing.data.factory import build_bar_provider
from swing.data.massive import MassiveBarProvider
from swing.data.throttle import RateLimiter

_FIXTURES = Path("tests/fixtures")
_NY = ZoneInfo("America/New_York")


def _payload(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def test_recorded_responses_return_split_adjusted_bars(tmp_path: Path):
    urls: list[str] = []

    def transport(url: str, headers: dict[str, str]):
        urls.append(url)
        assert headers["Authorization"] == "Bearer test-key"
        assert "test-key" not in url
        if "/v2/aggs/ticker/" in url and "adjusted=true" in url:
            return _payload("massive_aggs_adjusted.json")
        if "adjusted=false" in url or "/dividends" in url:
            raise AssertionError(url)
        if "/stocks/v1/splits" in url:
            assert "ticker=" not in url
            return _payload("massive_splits.json")
        raise AssertionError(url)

    provider = MassiveBarProvider(
        api_key="test-key",
        cache_dir=tmp_path,
        transport=transport,
        now=lambda: datetime(2024, 9, 3, 17, 0, tzinfo=_NY),
        limiter=RateLimiter(1000, sleep=lambda _seconds: None),
    )
    series = provider.fetch_daily("AAPL", 10)
    assert series.provider == "massive"
    assert series.adjustment == "split"
    assert series.corp_action_suspect is False
    assert [bar.session.isoformat() for bar in series.bars] == ["2024-08-29", "2024-08-30", "2024-09-03"]
    assert series.bars[0].close == 100.0
    assert series.bars[0].raw_close == 100.0
    assert series.bars[-1].open == 102.0
    assert all("finnhub" not in url for url in urls)
    assert all("candle" not in url for url in urls)


def test_missing_massive_key_is_a_typed_error(tmp_path: Path):
    cfg = SwingConfig.model_validate({"data": {"bars_provider": "massive"}})
    provider = build_bar_provider(cfg, env={}, cache_dir=tmp_path)
    with pytest.raises(MissingApiKeyError) as caught:
        provider.fetch_daily("AAPL", 5)
    assert caught.value.env_name == "MASSIVE_API_KEY"
    assert caught.value.code == "missing_api_key"
    assert "MASSIVE_API_KEY" in str(caught.value)


def test_vendor_error_redacts_the_api_key(tmp_path: Path):
    def transport(url: str, headers: dict[str, str]):
        raise RuntimeError("upstream said test-key is invalid")

    provider = MassiveBarProvider(
        api_key="test-key",
        cache_dir=tmp_path,
        transport=transport,
        limiter=RateLimiter(1000, sleep=lambda _seconds: None),
    )
    with pytest.raises(Exception) as caught:
        provider.fetch_daily("AAPL", 5)
    assert "test-key" not in str(caught.value)
    assert caught.value.code == "vendor_error"
