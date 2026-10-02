"""`~/.swing` is the data root. The old macOS folder is copied once and left in place."""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path


def swing_home(
    platform: str | None = None,
    home: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Return the swing data root.

    `SWING_HOME` wins, then the older `SWING_DATA_DIR` name. Otherwise the
    directory is `~/.swing` on every platform. `platform` is accepted so tests
    can inject it; the default path does not depend on it.
    """
    del platform
    environ = os.environ if env is None else env
    override = environ.get("SWING_HOME") or environ.get("SWING_DATA_DIR")
    if override:
        return Path(override).expanduser()
    root = Path.home() if home is None else home
    return root / ".swing"


def legacy_data_dir(platform: str | None = None, home: Path | None = None) -> Path | None:
    """The v0 macOS directory. Other platforms have no legacy folder."""
    system = sys.platform if platform is None else platform
    if system != "darwin":
        return None
    root = Path.home() if home is None else home
    return root / "Library" / "Application Support" / "swing"


def migrate_legacy_home(
    platform: str | None = None,
    home: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Copy the old macOS data directory into `~/.swing` when the new one is absent.

    The source is never deleted or rewritten. An explicit `SWING_HOME` or
    `SWING_DATA_DIR` is used as-is and is not a migration target.
    """
    dest = swing_home(platform=platform, home=home, env=env)
    environ = os.environ if env is None else env
    if environ.get("SWING_HOME") or environ.get("SWING_DATA_DIR"):
        return dest
    legacy = legacy_data_dir(platform=platform, home=home)
    if legacy is None or not legacy.is_dir() or dest.exists():
        return dest
    shutil.copytree(legacy, dest)
    return dest
