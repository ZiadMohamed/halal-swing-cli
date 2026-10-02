"""~/.swing is the data root. The old macOS folder is copied, never deleted."""

from pathlib import Path

from swing.home import migrate_legacy_home, swing_home
from swing.paths import bars_cache_dir, journal_path


def test_default_home_is_dot_swing_on_every_platform():
    home = Path("/Users/ziad")
    assert swing_home(platform="darwin", home=home, env={}) == home / ".swing"
    assert swing_home(platform="linux", home=Path("/home/ziad"), env={"XDG_DATA_HOME": "/tmp/xdg"}) == Path(
        "/home/ziad/.swing"
    )


def test_swing_home_overrides_the_older_data_dir_name():
    env = {"SWING_HOME": "/tmp/new", "SWING_DATA_DIR": "/tmp/old"}
    assert swing_home(platform="darwin", home=Path("/Users/ziad"), env=env) == Path("/tmp/new")
    assert bars_cache_dir(env={"SWING_DATA_DIR": "/tmp/old"}) == Path("/tmp/old/cache/bars")
    assert journal_path(env={"SWING_HOME": "/tmp/new"}) == Path("/tmp/new/journal.jsonl")


def test_migration_copies_the_macos_folder_and_leaves_it(tmp_path: Path):
    home = tmp_path / "Users" / "ziad"
    legacy = home / "Library" / "Application Support" / "swing"
    legacy.mkdir(parents=True)
    (legacy / "config.toml").write_text("max_concurrent_positions = 3\n", encoding="utf-8")
    (legacy / "journal.jsonl").write_text('{"ticker":"AAPL"}\n', encoding="utf-8")
    dest = migrate_legacy_home(platform="darwin", home=home, env={})
    assert dest == home / ".swing"
    assert (dest / "config.toml").read_text(encoding="utf-8").startswith("max_concurrent")
    assert (dest / "journal.jsonl").is_file()
    assert (legacy / "journal.jsonl").is_file()
    (dest / "config.toml").write_text("changed\n", encoding="utf-8")
    again = migrate_legacy_home(platform="darwin", home=home, env={})
    assert again == dest
    assert (dest / "config.toml").read_text(encoding="utf-8") == "changed\n"
    assert (legacy / "config.toml").read_text(encoding="utf-8").startswith("max_concurrent")


def test_explicit_home_is_not_a_migration_target(tmp_path: Path):
    home = tmp_path / "Users" / "ziad"
    legacy = home / "Library" / "Application Support" / "swing"
    legacy.mkdir(parents=True)
    (legacy / "config.toml").write_text("from-legacy\n", encoding="utf-8")
    dest = migrate_legacy_home(platform="darwin", home=home, env={"SWING_HOME": str(tmp_path / "elsewhere")})
    assert dest == tmp_path / "elsewhere"
    assert not dest.exists()
    assert (legacy / "config.toml").is_file()
