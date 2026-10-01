"""Locked defaults and config hash."""

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from swing.config import SwingConfig, load_config
from swing.hashing import config_hash


def test_defaults_match_locked_prefs():
    cfg = SwingConfig()
    assert cfg.schema_version == "1"
    assert cfg.account.mode == "cash"
    assert cfg.account.longs_only is True
    assert cfg.account.equity_usd is None
    assert cfg.risk.per_trade == 0.01
    assert cfg.heat.total_max == 0.06
    assert cfg.heat.sector_max == 0.03
    assert cfg.max_concurrent_positions == 4
    assert cfg.setups.mutex_order == ("BO_RVOL", "PB_EMA", "RSI2_MR")
    assert cfg.setups.rsi2_mr.rsi_period == 2
    assert cfg.setups.rsi2_mr.rsi_max == 10
    assert cfg.setups.rsi2_mr.sma_trend == 200
    assert cfg.setups.bo_rvol.rvol_min == 1.5
    assert cfg.setups.bo_rvol.breakout_lookback == 20
    assert cfg.setups.bo_rvol.sma_period == 50
    assert cfg.setups.pb_ema.ema_trend == 50
    assert cfg.setups.pb_ema.ema_touch == 20
    assert cfg.stops.atr_period == 14
    assert cfg.stops.atr_multiple == 1.5
    assert cfg.stops.reward_r == 2.0
    assert cfg.spy_r2.threshold == 0.70
    assert cfg.spy_r2.lookback_days == 60
    assert cfg.spy_r2.effect == "warn"
    assert cfg.earnings.strict is True
    assert cfg.earnings.blackout_before_days == 2
    assert cfg.earnings.blackout_after_days == 1
    assert cfg.exdiv.strict is False
    assert cfg.exdiv.block_yield_gte == 0.01
    assert cfg.output.compact is False
    assert cfg.data.bars_provider == "yfinance"
    assert cfg.data.events_provider == "finnhub"
    assert cfg.research.provider == "context"
    assert cfg.research.enabled is True
    assert cfg.research.affects_checklist_math is False
    assert cfg.journal.mode == "paper_jsonl"
    assert cfg.shariah.screen_in_v0 is False
    assert cfg.shariah.provider is None
    assert cfg.timezone.user == "Africa/Cairo"
    assert cfg.timezone.market == "America/New_York"


def test_finnhub_cannot_be_the_bars_provider():
    with pytest.raises(ValidationError):
        SwingConfig.model_validate({"data": {"bars_provider": "finnhub"}})


def test_research_cannot_affect_checklist_math():
    with pytest.raises(ValidationError):
        SwingConfig.model_validate({"research": {"affects_checklist_math": True}})


def test_unknown_config_key_is_rejected():
    with pytest.raises(ValidationError):
        SwingConfig.model_validate({"invented_edge": True})


def test_config_hash_is_sha256_of_canonical_json_and_changes_with_policy():
    cfg = SwingConfig()
    raw = json.dumps(
        cfg.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    assert config_hash(cfg) == digest
    assert config_hash(cfg) == config_hash(SwingConfig())
    changed = SwingConfig.model_validate({"risk": {"per_trade": 0.02}})
    assert config_hash(changed) != digest
    assert len(digest) == 64


def test_toml_override_keeps_other_defaults(tmp_path: Path):
    path = tmp_path / "swing.toml"
    path.write_text("max_concurrent_positions = 3\n", encoding="utf-8")
    cfg = load_config(path=path, env={})
    assert cfg.max_concurrent_positions == 3
    assert cfg.risk.per_trade == 0.01
    assert cfg.output.compact is False


def test_env_bars_provider_overrides_file(tmp_path: Path):
    path = tmp_path / "swing.toml"
    path.write_text('[data]\nbars_provider = "yfinance"\n', encoding="utf-8")
    cfg = load_config(path=path, env={"SWING_BARS_PROVIDER": "massive"})
    assert cfg.data.bars_provider == "massive"
    assert cfg.data.events_provider == "finnhub"


def test_example_config_matches_builtin_defaults():
    example = Path("config/swing.example.toml")
    loaded = load_config(path=example, env={})
    assert config_hash(loaded) == config_hash(SwingConfig())


def test_swing_data_dir_config_toml_is_loaded(tmp_path: Path):
    root = tmp_path / "moved"
    root.mkdir()
    (root / "config.toml").write_text("[risk]\nper_trade = 0.02\n", encoding="utf-8")
    cfg = load_config(env={"SWING_DATA_DIR": str(root)})
    assert cfg.risk.per_trade == 0.02
    assert cfg.heat.total_max == 0.06


def test_explicit_config_beats_data_dir(tmp_path: Path):
    root = tmp_path / "moved"
    root.mkdir()
    (root / "config.toml").write_text("[risk]\nper_trade = 0.02\n", encoding="utf-8")
    explicit = tmp_path / "other.toml"
    explicit.write_text("[risk]\nper_trade = 0.03\n", encoding="utf-8")
    cfg = load_config(path=explicit, env={"SWING_DATA_DIR": str(root)})
    assert cfg.risk.per_trade == 0.03


def test_locked_policy_cannot_be_relaxed():
    with pytest.raises(ValidationError):
        SwingConfig.model_validate({"spy_r2": {"effect": "block"}})
    with pytest.raises(ValidationError):
        SwingConfig.model_validate({"shariah": {"screen_in_v0": True}})
    with pytest.raises(ValidationError):
        SwingConfig.model_validate({"shariah": {"provider": "zoya"}})
    with pytest.raises(ValidationError):
        SwingConfig.model_validate({"account": {"longs_only": False}})
    with pytest.raises(ValidationError):
        SwingConfig.model_validate({"setups": {"mutex_order": ["RSI2_MR", "BO_RVOL", "PB_EMA"]}})
    with pytest.raises(ValidationError):
        SwingConfig.model_validate({"heat": {"total_max": 0.06, "sector_max": 0.07}})
    with pytest.raises(ValidationError):
        SwingConfig.model_validate({"stops": {"atr_period": 0}})


def test_data_table_must_be_a_table(tmp_path: Path):
    path = tmp_path / "swing.toml"
    path.write_text('data = "finnhub"\n', encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(path=path, env={"SWING_BARS_PROVIDER": "massive"})


def test_missing_explicit_config_errors(tmp_path: Path):
    missing = tmp_path / "nope.toml"
    with pytest.raises(FileNotFoundError):
        load_config(path=missing, env={})
