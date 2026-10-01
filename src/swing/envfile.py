"""Load project `.env` files without overriding the process environment."""

from __future__ import annotations

import os
from collections.abc import MutableMapping
from pathlib import Path

from dotenv import dotenv_values

from swing.paths import default_data_dir


def load_project_env(
    *,
    cwd: Path | None = None,
    environ: MutableMapping[str, str] | None = None,
    data_dir: Path | None = None,
    platform: str | None = None,
    home: Path | None = None,
) -> None:
    """Load `.env` from the working directory, then the swing data directory.

    A variable already present in the environment is left unchanged. The
    working-directory file wins over the data-directory file. `SWING_DATA_DIR`
    set by the working-directory file is used when locating that second file.
    On macOS the data directory is `~/Library/Application Support/swing`.
    """
    target: MutableMapping[str, str] = os.environ if environ is None else environ
    root = Path.cwd() if cwd is None else cwd
    _merge_file(root / ".env", target)
    folder = data_dir if data_dir is not None else default_data_dir(platform=platform, home=home, env=target)
    _merge_file(folder / ".env", target)


def _merge_file(path: Path, target: MutableMapping[str, str]) -> None:
    if not path.is_file():
        return
    parsed = dotenv_values(path)
    for key, value in parsed.items():
        if not key or value is None or key in target:
            continue
        target[key] = value
