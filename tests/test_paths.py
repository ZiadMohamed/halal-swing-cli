"""macOS is the path target. Other platforms are an explicit fallback."""

from pathlib import Path

from swing.paths import default_data_dir


def test_macos_uses_application_support():
    path = default_data_dir(platform="darwin", home=Path("/Users/ziad"), env={})
    assert path == Path("/Users/ziad/Library/Application Support/swing")


def test_linux_fallback_is_labeled_by_using_xdg():
    path = default_data_dir(
        platform="linux",
        home=Path("/home/ziad"),
        env={"XDG_DATA_HOME": "/home/ziad/.local/share"},
    )
    assert path == Path("/home/ziad/.local/share/swing")


def test_swing_data_dir_overrides_platform():
    path = default_data_dir(
        platform="darwin",
        home=Path("/Users/ziad"),
        env={"SWING_DATA_DIR": "/tmp/swing-data"},
    )
    assert path == Path("/tmp/swing-data")
