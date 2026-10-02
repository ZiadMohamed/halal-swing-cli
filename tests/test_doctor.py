"""Doctor classifies key and data failures with a fix line. No network."""

from datetime import date
from pathlib import Path

from swing.data.errors import VendorError
from swing.doctor import mask_secret, render_findings, run_doctor


def _run(tmp_path: Path, env: dict[str, str], probe=None, **kwargs):
    return run_doctor(env=env, home=tmp_path, cwd=tmp_path, today=date(2026, 10, 2), probe=probe, **kwargs)


def test_missing_key_401_403_and_429_each_have_a_fix(tmp_path: Path):
    def probe(name: str, endpoint: str):
        if name == "FINNHUB_API_KEY":
            raise VendorError("no", kind="invalid_key", endpoint=endpoint, status=401)
        raise VendorError("limit", kind="rate_limited", endpoint=endpoint, status=429)

    def forbid(name: str, endpoint: str):
        del name, endpoint
        raise VendorError("no access", kind="plan_forbidden", endpoint="/calendar/earnings", status=403)

    forbidden = _run(tmp_path, {"FINNHUB_API_KEY": "abcdefghijklmnop"}, probe=forbid)
    text = render_findings(forbidden)
    assert "plan_forbidden" in text
    assert "HTTP 403" in text
    assert "abcdefghijklmnop" not in text
    assert mask_secret("abcdefghijklmnop") in text

    missing = render_findings(_run(tmp_path, {}))
    assert "FINNHUB_API_KEY" in missing
    assert "Set FINNHUB_API_KEY" in missing
    assert "MASSIVE_API_KEY" in missing
    assert "required" in missing
    assert "stays yfinance" in missing
    assert "CONTEXT_DEV" not in missing

    rated = render_findings(_run(tmp_path, {"FINNHUB_API_KEY": "abcdefghijklmnop", "MASSIVE_API_KEY": "massive-key-1234"}, probe=probe))
    assert "invalid_key" in rated
    assert "HTTP 401" in rated
    assert "rate_limited" in rated
    assert "HTTP 429" in rated
    assert "massive-key-1234" not in rated


def test_stale_nan_and_malformed_book(tmp_path: Path):
    stale = render_findings(
        _run(tmp_path, {}, last_session=date(2026, 10, 1), spy_session=date(2026, 9, 30))
    )
    assert "stale" in stale
    nan = render_findings(_run(tmp_path, {}, spy_nan=True))
    assert "non-finite" in nan
    assert "NaN" in nan
    (tmp_path / "book.jsonl").write_text("{not json}\n", encoding="utf-8")
    book = render_findings(_run(tmp_path, {}))
    assert "book line 1" in book
    assert "not rewritten" in book


def test_doctor_names_the_home_and_the_fill_count(tmp_path: Path):
    text = render_findings(_run(tmp_path, {}))
    assert f"home: {tmp_path}" in text
    assert "account.mode is cash" in text
    assert "does not send orders" in text
    assert "0 open lots; 0 closed fills" in text
    assert "0.005" in text
    assert "built-in stays 0.01" in text


def test_universe_copy_states_the_floor_without_blocking(tmp_path: Path):
    missing = render_findings(_run(tmp_path, {}))
    assert "Floor is 20 names, target 30–50" in missing
    assert "TICKER ETF" in missing
    assert "SPY" in missing

    short = tmp_path / "short"
    short.mkdir()
    (short / "universe.txt").write_text("AAPL\nMSFT\nUMMA ETF\n", encoding="utf-8")
    thin = _run(short, {})
    universe = next(item for item in thin if item.name == "universe")
    assert universe.ok is True
    text = render_findings(thin)
    assert "Thin universe" in text
    assert "3 tickers" in text

    wide = tmp_path / "wide"
    wide.mkdir()
    names = "\n".join(f"N{i:02d}" for i in range(20)) + "\nSPY\n"
    (wide / "universe.txt").write_text(names, encoding="utf-8")
    listed = _run(wide, {})
    found = next(item for item in listed if item.name == "universe")
    assert found.ok is True
    shown = render_findings(listed)
    assert "Thin universe" not in shown
    assert "SPY is listed" in shown


def test_nested_clone_warning(tmp_path: Path):
    outer = tmp_path / "outer"
    inner = outer / "halal-swing-cli"
    inner.mkdir(parents=True)
    (inner / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    findings = run_doctor(env={}, home=tmp_path, cwd=outer, today=date(2026, 10, 2))
    text = render_findings(findings)
    assert "inner" in text
    assert "halal-swing-cli" in text
