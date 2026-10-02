"""Operator docs point at the Section 8 answers. The live example stays on v0 defaults."""

from pathlib import Path

from swing.config import SwingConfig, load_config
from swing.hashing import config_hash

_ROOT = Path(__file__).resolve().parents[1]


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
