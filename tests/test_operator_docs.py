"""Operator docs point at the Section 8 answers. The live example stays on v0 defaults."""

import tomllib
from pathlib import Path

import pytest
from pydantic import ValidationError

from swing.config import SwingConfig, load_config
from swing.hashing import config_hash

_ROOT = Path(__file__).resolve().parents[1]


def test_env_example_requires_both_free_keys_and_keeps_yfinance():
    example = (_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "FINNHUB_API_KEY" in example
    assert "MASSIVE_API_KEY" in example
    assert "Required" in example
    assert "stays yfinance" in example
    assert "CONTEXT_DEV" not in example
    assert "Context.dev is not a dependency" in example
    readme = (_ROOT / "README.md").read_text(encoding="utf-8")
    assert "Doctor requires both free keys" in readme
    assert "CONTEXT_DEV" not in readme


def test_readme_records_the_satellite_operator_file():
    readme = (_ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/decisions/SECTION8_ANSWERS.md" in readme
    assert "satellite sleeve" in readme
    assert "20% of total USD equity" in readme
    assert "0.005" in readme
    assert "20 closed real fills" in readme
    assert 'benchmark.symbol' in readme
    assert '"SPUS"' in readme
    assert "out of `universe.txt`" in readme
    assert "does not rank" in readme
    assert "at least 20 user-screened USD stocks" in readme
    assert "30–50" in readme
    assert "`TICKER ETF`" in readme
    assert "SPY stays out of the file" in readme
    research = readme.split("## Research data", 1)[1].split("## Tests", 1)[0]
    assert "Sharadar Prices, full history" in research
    assert "(SEP)" in research
    assert "live scan path" in research
    assert "pre-registered" in research


def test_example_config_still_matches_builtin_defaults():
    example = _ROOT / "config" / "swing.example.toml"
    text = example.read_text(encoding="utf-8")
    assert "satellite sleeve" in text
    assert "0.005" in text
    assert "SECTION8_ANSWERS.md" in text
    loaded = load_config(path=example, env={})
    assert loaded.account.equity_usd is None
    assert loaded.risk.per_trade == 0.01
    assert loaded.account.mode == "cash"
    assert loaded.data.bars_provider == "yfinance"
    assert config_hash(loaded) == config_hash(SwingConfig())


def test_v1_surface_example_is_recorded_and_not_loaded():
    path = _ROOT / "config" / "v1-surface.example.toml"
    text = path.read_text(encoding="utf-8")
    assert "Not wired to swing analyze" in text
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    assert data["portfolio"] == {"slots": 5, "max_position_frac": 0.20}
    assert data["regime"] == {"gate": True, "symbol": "SPY", "sma": 200}
    assert data["trend"] == {"sma": 200}
    assert data["rank"] == {"lookback": 126, "skip": 5}
    assert data["exit"] == {"mode": "trail", "trail_atr": 3.0, "target_r": 2.0}
    assert data["entry"] == {"cap_atr": 1.0}
    assert data["stops"] == {"atr_period": 14, "initial_atr": 1.5}
    assert data["earnings"] == {"strict": True, "min_room_sessions": 3, "after_days": 1}
    assert data["liquidity"] == {"min_price": 5, "min_median_dollar_volume": 10000000}
    assert data["benchmark"] == {"symbol": "SPUS"}
    with pytest.raises(ValidationError):
        load_config(path=path, env={})
    readme = (_ROOT / "README.md").read_text(encoding="utf-8")
    assert "not wired" in readme
    assert "config/v1-surface.example.toml" in readme
    assert "portfolio.slots" in readme
