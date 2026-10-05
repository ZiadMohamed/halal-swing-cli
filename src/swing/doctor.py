"""Local health checks. Live probes run only when a key is set and a probe is supplied."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from swing.book import closed_trades, load_book
from swing.data.errors import VendorError, fix_line
from swing.home import swing_home


@dataclass(frozen=True)
class Finding:
    name: str
    ok: bool
    detail: str
    fix: str | None = None


def run_doctor(
    *,
    env: dict[str, str],
    home: Path,
    cwd: Path,
    today: date,
    last_session: date | None = None,
    spy_session: date | None = None,
    spy_nan: bool = False,
    probe=None,
) -> list[Finding]:
    findings = [
        Finding("python", True, f"{sys.version.split()[0]} {sys.executable}"),
        Finding("home", True, str(home)),
        _env_files(env, home, cwd),
        Finding(
            "cash",
            True,
            "account.mode is cash. Size from settled cash, not buying power. This program does not send orders.",
        ),
        _nested_clone(cwd),
        _book(home),
        _spy(last_session, spy_session, spy_nan),
    ]
    findings.extend(_keys(env, probe))
    return findings


def render_findings(findings: list[Finding]) -> str:
    lines = []
    for item in findings:
        mark = "ok" if item.ok else "fix"
        lines.append(f"{mark}  {item.name}: {item.detail}")
        if item.fix:
            lines.append(f"     fix: {item.fix}")
    return "\n".join(lines) + "\n"


def mask_secret(value: str) -> str:
    if len(value) < 8:
        return "set"
    return f"…{value[-4:]}"


def _env_files(env: dict[str, str], home: Path, cwd: Path) -> Finding:
    loaded = []
    if (cwd / ".env").is_file():
        loaded.append(str(cwd / ".env"))
    if (home / ".env").is_file():
        loaded.append(str(home / ".env"))
    keys = []
    for name in ("FINNHUB_API_KEY", "MASSIVE_API_KEY"):
        raw = env.get(name, "").strip()
        keys.append(f"{name} {'missing' if not raw else mask_secret(raw)}")
    where = ", ".join(loaded) if loaded else "no .env file"
    return Finding("env", True, f"{where}; " + "; ".join(keys))


_REQUIRED_KEYS = (
    (
        "FINNHUB_API_KEY",
        "/calendar/earnings",
        "Set FINNHUB_API_KEY in the shell or ~/.swing/.env. "
        "The free Finnhub key is required for /calendar/earnings. "
        "Context.dev is not a dependency.",
    ),
    (
        "MASSIVE_API_KEY",
        "/v2/aggs/grouped",
        "Set MASSIVE_API_KEY in the shell or ~/.swing/.env. "
        "The free Massive key is required. "
        "data.bars_provider stays yfinance until SWING_BARS_PROVIDER=massive. "
        "A missing Massive key does not block a fresh yfinance bar.",
    ),
)


def _keys(env: dict[str, str], probe) -> list[Finding]:
    found = []
    for name, endpoint, required_fix in _REQUIRED_KEYS:
        raw = env.get(name, "").strip()
        if not raw:
            found.append(Finding(name, False, "required", required_fix))
            continue
        if probe is None:
            found.append(Finding(name, True, f"set {mask_secret(raw)}; probe skipped"))
            continue
        try:
            probe(name, endpoint)
        except VendorError as exc:
            found.append(
                Finding(
                    name,
                    False,
                    f"{exc.endpoint or endpoint}: {exc.kind}",
                    fix_line(exc.kind, name),
                )
            )
        else:
            found.append(Finding(name, True, f"{endpoint} ok"))
    return found


def _book(home: Path) -> Finding:
    path = home / "book.jsonl"
    try:
        events, lots = load_book(path)
    except ValueError as exc:
        return Finding("book", False, str(exc), "Fix that line. The file was not rewritten.")
    closed = len(closed_trades(events))
    detail = f"{len(lots)} open lots; {closed} closed fills"
    if closed < 20:
        detail += (
            ". Set risk.per_trade to 0.005 in ~/.swing/config.toml until 20 closed real fills, then 0.01. "
            "The built-in stays 0.01."
        )
    else:
        detail += ". Operator risk.per_trade can stay 0.01. The built-in stays 0.01."
    return Finding("book", True, detail)


def _spy(last_session: date | None, spy_session: date | None, spy_nan: bool) -> Finding:
    if spy_nan:
        return Finding(
            "spy",
            False,
            "SPY cache has a non-finite price",
            "Delete the SPY cache file and fetch again. A NaN bar is not a price.",
        )
    if last_session is None or spy_session is None:
        return Finding("spy", False, "no SPY cache", "Fetch SPY after the NYSE close. The signal needs that session.")
    if spy_session != last_session:
        return Finding(
            "spy",
            False,
            f"SPY cache ends {spy_session.isoformat()}, last session is {last_session.isoformat()}",
            "Fetch again after the close. Do not trade on a stale bar.",
        )
    return Finding("spy", True, f"SPY through {spy_session.isoformat()}")


def _nested_clone(cwd: Path) -> Finding:
    child = cwd / "halal-swing-cli" / "pyproject.toml"
    if child.is_file() and not (cwd / "pyproject.toml").is_file():
        return Finding(
            "path",
            False,
            "This folder contains halal-swing-cli/ but is not the project.",
            "cd into the inner halal-swing-cli directory before uv tool install.",
        )
    return Finding("path", True, str(cwd))


def default_home() -> Path:
    return swing_home()
