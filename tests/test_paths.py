"""macOS is the path target. Other platforms are an explicit fallback."""

from pathlib import Path

from swing.paths import bars_cache_dir, default_data_dir, journal_path


def test_macos_uses_dot_swing():
    path = default_data_dir(platform="darwin", home=Path("/Users/ziad"), env={})
    assert path == Path("/Users/ziad/.swing")


def test_linux_uses_the_same_dot_swing_root():
    path = default_data_dir(
        platform="linux",
        home=Path("/home/ziad"),
        env={"XDG_DATA_HOME": "/home/ziad/.local/share"},
    )
    assert path == Path("/home/ziad/.swing")


def test_cache_and_journal_follow_the_data_dir():
    env = {"SWING_DATA_DIR": "/tmp/swing-data"}
    assert bars_cache_dir(platform="darwin", home=Path("/Users/ziad"), env=env) == Path(
        "/tmp/swing-data/cache/bars"
    )
    assert journal_path(platform="darwin", home=Path("/Users/ziad"), env=env) == Path(
        "/tmp/swing-data/journal.jsonl"
    )


def test_swing_data_dir_overrides_platform():
    path = default_data_dir(
        platform="darwin",
        home=Path("/Users/ziad"),
        env={"SWING_DATA_DIR": "/tmp/swing-data"},
    )
    assert path == Path("/tmp/swing-data")
