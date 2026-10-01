"""Filesystem roots. macOS is the product target."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path


def default_data_dir(
    platform: str | None = None,
    home: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Return the swing data root.

    macOS: ~/Library/Application Support/swing
    Other OS (CI and this agent's Linux VM): $XDG_DATA_HOME/swing or
    ~/.local/share/swing. That fallback is not the supported daily-driver layout.
    SWING_DATA_DIR overrides both.
    """
    environ = os.environ if env is None else env
    override = environ.get("SWING_DATA_DIR")
    if override:
        return Path(override).expanduser()
    system = sys.platform if platform is None else platform
    root = Path.home() if home is None else home
    if system == "darwin":
        return root / "Library" / "Application Support" / "swing"
    xdg = environ.get("XDG_DATA_HOME")
    base = Path(xdg).expanduser() if xdg else root / ".local" / "share"
    return base / "swing"


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
    """JSONL path for Chat 5. The file is not created here."""
    return default_data_dir(platform=platform, home=home, env=env) / "journal.jsonl"
