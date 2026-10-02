"""`.env` loads at startup. Process environment wins. Files stay out of git."""

import subprocess
from pathlib import Path

from swing.envfile import load_project_env

_ROOT = Path(__file__).resolve().parents[1]

_EXAMPLE_KEYS = (
    "FINNHUB_API_KEY",
    "MASSIVE_API_KEY",
    "SWING_BARS_PROVIDER",
    "SWING_HOME",
    "SWING_CONFIG",
    "SWING_DATA_DIR",
)


def test_cwd_dotenv_fills_missing_keys_and_keeps_comments(tmp_path):
    cwd = tmp_path / "proj"
    cwd.mkdir()
    (cwd / ".env").write_text(
        "\n".join(
            [
                "# earnings calendar only",
                'export FINNHUB_API_KEY="fh-test"',
                "MASSIVE_API_KEY=massive-test",
                "",
            ]
        ),
        encoding="utf-8",
    )
    env: dict[str, str] = {}
    load_project_env(cwd=cwd, environ=env, data_dir=tmp_path / "missing-data")
    assert env["FINNHUB_API_KEY"] == "fh-test"
    assert env["MASSIVE_API_KEY"] == "massive-test"


def test_process_environment_wins_over_dotenv_files(tmp_path):
    cwd = tmp_path / "proj"
    data = tmp_path / "data"
    cwd.mkdir()
    data.mkdir()
    (cwd / ".env").write_text("FINNHUB_API_KEY=from-cwd\nMASSIVE_API_KEY=from-cwd\n", encoding="utf-8")
    (data / ".env").write_text("FINNHUB_API_KEY=from-data\n", encoding="utf-8")
    env = {"FINNHUB_API_KEY": "from-shell"}
    load_project_env(cwd=cwd, environ=env, data_dir=data)
    assert env["FINNHUB_API_KEY"] == "from-shell"
    assert env["MASSIVE_API_KEY"] == "from-cwd"


def test_data_dir_fills_keys_the_cwd_file_omits(tmp_path):
    cwd = tmp_path / "proj"
    data = tmp_path / "data"
    cwd.mkdir()
    data.mkdir()
    (cwd / ".env").write_text("FINNHUB_API_KEY=from-cwd\n", encoding="utf-8")
    (data / ".env").write_text(
        "FINNHUB_API_KEY=from-data\nMASSIVE_API_KEY=from-data\nSWING_BARS_PROVIDER=massive\n",
        encoding="utf-8",
    )
    env: dict[str, str] = {}
    load_project_env(cwd=cwd, environ=env, data_dir=data)
    assert env["FINNHUB_API_KEY"] == "from-cwd"
    assert env["MASSIVE_API_KEY"] == "from-data"
    assert env["SWING_BARS_PROVIDER"] == "massive"


def test_swing_data_dir_in_the_cwd_file_selects_the_data_dotenv(tmp_path):
    data = tmp_path / "custom swing"
    data.mkdir()
    (data / ".env").write_text("MASSIVE_API_KEY=custom\n", encoding="utf-8")
    cwd = tmp_path / "proj"
    cwd.mkdir()
    (cwd / ".env").write_text(f'SWING_DATA_DIR="{data}"\n', encoding="utf-8")
    env: dict[str, str] = {}
    load_project_env(cwd=cwd, environ=env, platform="darwin", home=tmp_path / "home")
    assert env["SWING_DATA_DIR"] == str(data)
    assert env["MASSIVE_API_KEY"] == "custom"


def test_dot_swing_dotenv_is_loaded(tmp_path):
    home = tmp_path / "Users" / "ziad"
    data = home / ".swing"
    data.mkdir(parents=True)
    (data / ".env").write_text("FINNHUB_API_KEY=mac-key\n", encoding="utf-8")
    cwd = tmp_path / "proj"
    cwd.mkdir()
    env: dict[str, str] = {}
    load_project_env(cwd=cwd, environ=env, platform="darwin", home=home)
    assert env["FINNHUB_API_KEY"] == "mac-key"


def test_missing_dotenv_files_leave_the_environment_alone(tmp_path):
    env = {"SWING_BARS_PROVIDER": "yfinance"}
    load_project_env(cwd=tmp_path / "absent", environ=env, data_dir=tmp_path / "also-absent")
    assert env == {"SWING_BARS_PROVIDER": "yfinance"}


def test_env_example_documents_keys_and_git_ignores_secrets():
    example = _ROOT / ".env.example"
    text = example.read_text(encoding="utf-8")
    for key in _EXAMPLE_KEYS:
        assert key in text
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        _, _, value = stripped.partition("=")
        assert value.strip().strip('"').strip("'") == ""
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", ".env"],
        cwd=_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert ignored.returncode == 0
    visible = subprocess.run(
        ["git", "check-ignore", "-q", ".env.example"],
        cwd=_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert visible.returncode == 1


def test_readme_tells_you_to_copy_the_example_and_analyze():
    readme = (_ROOT / "README.md").read_text(encoding="utf-8")
    assert "cp .env.example .env" in readme
    assert "swing analyze" in readme
    assert "--explain" in readme
    assert "CONTEXT_DEV" not in readme
