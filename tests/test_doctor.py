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


def test_doctor_does_not_read_a_universe_file(tmp_path: Path):
    missing = render_findings(_run(tmp_path, {}))
    assert "universe" not in missing.lower()
    assert "Floor is 20" not in missing
    (tmp_path / "universe.txt").write_text("AAPL\nMSFT\nUMMA ETF\nSPY\n", encoding="utf-8")
    again = render_findings(_run(tmp_path, {}))
    assert again == missing
    assert all(item.name != "universe" for item in _run(tmp_path, {}))


def test_nested_clone_warning(tmp_path: Path):
    outer = tmp_path / "outer"
    inner = outer / "halal-swing-cli"
    inner.mkdir(parents=True)
    (inner / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    findings = run_doctor(env={}, home=tmp_path, cwd=outer, today=date(2026, 10, 2))
    text = render_findings(findings)
    assert "inner" in text
    assert "halal-swing-cli" in text
