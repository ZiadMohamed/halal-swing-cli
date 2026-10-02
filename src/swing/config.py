"""Locked checklist policy. Defaults match prefs 1–12 (2026-10-01)."""

from __future__ import annotations

import os
import sys
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from swing.hashing import config_hash as hash_config

_MUTEX = ("BO_RVOL", "PB_EMA", "RSI2_MR")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AccountConfig(_Strict):
    mode: Literal["cash"] = "cash"
    longs_only: Literal[True] = True
    equity_usd: float | None = Field(default=None, ge=0)


class RiskConfig(_Strict):
    per_trade: float = Field(default=0.01, gt=0, le=1)


class HeatConfig(_Strict):
    total_max: float = Field(default=0.06, gt=0, le=1)
    sector_max: float = Field(default=0.03, gt=0, le=1)

    @model_validator(mode="after")
    def _sector_within_total(self) -> HeatConfig:
        if self.sector_max > self.total_max:
            raise ValueError("sector heat cannot exceed total heat")
        return self


class BoRvolConfig(_Strict):
    rvol_min: float = Field(default=1.5, gt=0)
    breakout_lookback: int = Field(default=20, ge=1)
    sma_period: int = Field(default=50, ge=1)


class PbEmaConfig(_Strict):
    ema_trend: int = Field(default=50, ge=1)
    ema_touch: int = Field(default=20, ge=1)


class Rsi2Config(_Strict):
    rsi_period: int = Field(default=2, ge=1)
    rsi_max: int = Field(default=10, ge=1, le=100)
    sma_trend: int = Field(default=200, ge=1)


class SetupsConfig(_Strict):
    mutex_order: tuple[str, ...] = _MUTEX
    bo_rvol: BoRvolConfig = Field(default_factory=BoRvolConfig)
    pb_ema: PbEmaConfig = Field(default_factory=PbEmaConfig)
    rsi2_mr: Rsi2Config = Field(default_factory=Rsi2Config)

    @field_validator("mutex_order")
    @classmethod
    def _locked_mutex(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if tuple(value) != _MUTEX:
            raise ValueError("mutex order is locked: BO_RVOL > PB_EMA > RSI2_MR")
        return _MUTEX


class StopsConfig(_Strict):
    atr_period: int = Field(default=14, ge=1)
    atr_multiple: float = Field(default=1.5, gt=0)
    reward_r: float = Field(default=2.0, gt=0)


class EarningsConfig(_Strict):
    strict: bool = True
    blackout_before_days: int = 2
    blackout_after_days: int = 1


class ExDivConfig(_Strict):
    """strict off: ordinary ex-div warns. Yield at or above block_yield_gte still blocks."""

    strict: bool = False
    block_yield_gte: float = 0.01


class DataConfig(_Strict):
    bars_provider: Literal["yfinance", "massive"] = "yfinance"
    events_provider: Literal["finnhub"] = "finnhub"


class JournalConfig(_Strict):
    mode: Literal["paper_jsonl"] = "paper_jsonl"


class ShariahConfig(_Strict):
    screen_in_v0: Literal[False] = False
    provider: Literal[None] = None


class TimezoneConfig(_Strict):
    user: str = "Africa/Cairo"
    market: str = "America/New_York"


class SwingConfig(_Strict):
    schema_version: Literal["1"] = "1"
    account: AccountConfig = Field(default_factory=AccountConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    heat: HeatConfig = Field(default_factory=HeatConfig)
    max_concurrent_positions: int = Field(default=4, ge=1)
    setups: SetupsConfig = Field(default_factory=SetupsConfig)
    stops: StopsConfig = Field(default_factory=StopsConfig)
    earnings: EarningsConfig = Field(default_factory=EarningsConfig)
    exdiv: ExDivConfig = Field(default_factory=ExDivConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    journal: JournalConfig = Field(default_factory=JournalConfig)
    shariah: ShariahConfig = Field(default_factory=ShariahConfig)
    timezone: TimezoneConfig = Field(default_factory=TimezoneConfig)

    def config_hash(self) -> str:
        return hash_config(self)


def resolve_config_path(env: Mapping[str, str], *, discover_files: bool) -> Path | None:
    """Resolve a config file.

    Order: SWING_CONFIG, ./swing.toml (only when discovering), SWING_DATA_DIR/config.toml,
    then the platform file. An explicit load_config(path=...) never reaches this.
    """
    raw = env.get("SWING_CONFIG")
    if raw:
        return Path(raw).expanduser()
    if discover_files:
        cwd_file = Path.cwd() / "swing.toml"
        if cwd_file.is_file():
            return cwd_file
    data_dir = env.get("SWING_DATA_DIR")
    if data_dir:
        relocated = Path(data_dir).expanduser() / "config.toml"
        if relocated.is_file():
            return relocated
    if not discover_files:
        return None
    home = Path.home()
    if sys.platform == "darwin":
        mac = home / "Library" / "Application Support" / "swing" / "config.toml"
        return mac if mac.is_file() else None
    xdg_root = env.get("XDG_CONFIG_HOME")
    base = Path(xdg_root).expanduser() if xdg_root else home / ".config"
    other = base / "swing" / "config.toml"
    return other if other.is_file() else None


def load_config(path: Path | None = None, env: Mapping[str, str] | None = None) -> SwingConfig:
    """Load policy. An explicit env mapping does not scan the home directory.

    The real CLI calls this with env=None so macOS config discovery runs.
    Tests pass env={} and stay on built-in defaults unless they pass a path.
    """
    discover_files = env is None and path is None
    environ: Mapping[str, str] = os.environ if env is None else env
    if path is None:
        path = resolve_config_path(environ, discover_files=discover_files)
    data: dict[str, Any] = {}
    if path is not None:
        if not path.is_file():
            raise FileNotFoundError(f"Config file not found: {path}")
        with path.open("rb") as handle:
            loaded = tomllib.load(handle)
        if not isinstance(loaded, dict):
            raise ValueError("Config root must be a TOML table")
        data = loaded
    provider = environ.get("SWING_BARS_PROVIDER")
    if provider:
        current = data.get("data") or {}
        if not isinstance(current, dict):
            raise ValueError("Config key 'data' must be a table")
        current = dict(current)
        current["bars_provider"] = provider
        data["data"] = current
    return SwingConfig.model_validate(data)
