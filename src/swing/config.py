"""Locked checklist policy. Defaults match prefs 1–12 (2026-10-01)."""

from __future__ import annotations

import os
import sys
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from swing.hashing import config_hash as hash_config

_MUTEX = ("BO_RVOL", "PB_EMA", "RSI2_MR")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AccountConfig(_Strict):
    mode: Literal["cash", "margin"] = "cash"
    longs_only: Literal[True] = True
    equity_usd: float | None = Field(default=None, ge=0)


class RiskConfig(_Strict):
    per_trade: float = Field(default=0.01, gt=0, le=1)


class HeatConfig(_Strict):
    total_max: float = Field(default=0.06, gt=0, le=1)
    sector_max: float = Field(default=0.03, gt=0, le=1)


class BoRvolConfig(_Strict):
    rvol_min: float = 1.5
    breakout_lookback: int = 20
    sma_period: int = 50


class PbEmaConfig(_Strict):
    ema_trend: int = 50
    ema_touch: int = 20


class Rsi2Config(_Strict):
    rsi_period: int = 2
    rsi_max: int = 10
    sma_trend: int = 200


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
    atr_period: int = 14
    atr_multiple: float = 1.5
    reward_r: float = 2.0


class SpyR2Config(_Strict):
    threshold: float = 0.70
    lookback_days: int = 60
    effect: Literal["warn"] = "warn"


class EarningsConfig(_Strict):
    strict: bool = True
    blackout_before_days: int = 2
    blackout_after_days: int = 1


class ExDivConfig(_Strict):
    """strict off: ordinary ex-div warns. Yield at or above block_yield_gte still blocks."""

    strict: bool = False
    block_yield_gte: float = 0.01


class OutputConfig(_Strict):
    compact: bool = False


class DataConfig(_Strict):
    bars_provider: Literal["yfinance", "massive"] = "yfinance"
    events_provider: Literal["finnhub"] = "finnhub"


class ResearchConfig(_Strict):
    provider: Literal["context"] = "context"
    enabled: bool = True
    affects_checklist_math: Literal[False] = False


class JournalConfig(_Strict):
    mode: Literal["paper_jsonl"] = "paper_jsonl"


class ShariahConfig(_Strict):
    screen_in_v0: Literal[False] = False
    provider: str | None = None


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
    spy_r2: SpyR2Config = Field(default_factory=SpyR2Config)
    earnings: EarningsConfig = Field(default_factory=EarningsConfig)
    exdiv: ExDivConfig = Field(default_factory=ExDivConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    research: ResearchConfig = Field(default_factory=ResearchConfig)
    journal: JournalConfig = Field(default_factory=JournalConfig)
    shariah: ShariahConfig = Field(default_factory=ShariahConfig)
    timezone: TimezoneConfig = Field(default_factory=TimezoneConfig)

    def config_hash(self) -> str:
        return hash_config(self)


def resolve_config_path(env: Mapping[str, str], *, discover_files: bool) -> Path | None:
    raw = env.get("SWING_CONFIG")
    if raw:
        return Path(raw).expanduser()
    if not discover_files:
        return None
    cwd_file = Path.cwd() / "swing.toml"
    if cwd_file.is_file():
        return cwd_file
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
        current = dict(data.get("data") or {})
        current["bars_provider"] = provider
        data["data"] = current
    return SwingConfig.model_validate(data)
