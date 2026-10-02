"""Filesystem roots. The product directory is `~/.swing`."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from swing.home import swing_home


def default_data_dir(
    platform: str | None = None,
    home: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Return the swing data root. See `swing.home.swing_home`."""
    return swing_home(platform=platform, home=home, env=env)


def bars_cache_dir(
    platform: str | None = None,
    home: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Parquet root for Chat 2. Nothing is written in the skeleton."""
    return default_data_dir(platform=platform, home=home, env=env) / "cache" / "bars"


def journal_path(
    platform: str | None = None,
    home: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Paper JSONL path. This helper does not create the file."""
    return default_data_dir(platform=platform, home=home, env=env) / "journal.jsonl"
