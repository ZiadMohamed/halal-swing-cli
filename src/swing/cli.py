"""Terminal entrypoint."""

from __future__ import annotations

import argparse
import logging
import math
import sys
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from swing import __version__
from swing.analyze import analyze
from swing.home import migrate_legacy_home
from swing.codes import ReasonCode
from swing.config import load_config
from swing.envfile import load_project_env
from swing.journal.paper import PaperJournal
from swing.output.render import render_json, render_text


def main(argv: list[str] | None = None) -> int:
    migrate_legacy_home()
    load_project_env()
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command != "analyze":
        parser.print_help(sys.stderr)
        return 2
    _configure_logging(args.verbose)
    try:
        config = load_config(path=args.config)
        journal = PaperJournal()
        positions = journal.load_positions()
        envelope = analyze(
            args.ticker,
            config=config,
            fetch_market=True,
            positions=positions,
            sector=_sector(args.sector),
            equity_usd=args.equity,
            earnings_date=args.earnings_date,
        )
    except (ValueError, ValidationError, FileNotFoundError) as exc:
        print(exc, file=sys.stderr)
        return 2
    hint = _journal_hint(envelope, journal.path, len(positions))
    if hint:
        print(hint, file=sys.stderr)
    if args.json:
        sys.stdout.write(render_json(envelope))
    else:
        sys.stdout.write(
            render_text(
                envelope,
                explain=bool(args.explain),
                user_tz=config.timezone.user,
                market_tz=config.timezone.market,
                config=config,
            )
        )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="swing",
        description="Personal cash-long swing checklist. Not financial advice. Not a Shariah certification.",
    )
    parser.add_argument("--version", action="version", version=f"swing {__version__}")
    sub = parser.add_subparsers(dest="command")
    analyze_parser = sub.add_parser(
        "analyze",
        help="Evaluate one ticker and print a decision envelope",
        description=(
            "Personal cash-long swing checklist. Not financial advice. Not a Shariah certification. "
            "Money is USD. There is no other currency and no FX conversion. "
            "On ENTER_LONG the text says when to buy and when to sell. "
            "You type the cash long in Interactive Brokers yourself. This CLI does not send orders."
        ),
    )
    analyze_parser.add_argument("ticker", help="US equity ticker you have already screened (example: AAPL)")
    analyze_parser.add_argument("--json", action="store_true", help="Print the decision envelope as JSON")
    analyze_parser.add_argument(
        "--explain",
        action="store_true",
        help="Print every gate and the longer buy and sell numbers. Ignored when --json is set.",
    )
    analyze_parser.add_argument("--config", type=Path, help="TOML config file. Overrides discovery.")
    analyze_parser.add_argument(
        "--equity",
        type=_usd_equity,
        default=None,
        metavar="USD",
        help=(
            "Account equity in USD for this run. Overrides [account].equity_usd. "
            "Does not change config_hash. v0 does not convert other currencies. "
            "If neither this flag nor the TOML value is set, "
            "the decision stays NO_TRADE / EQUITY_UNSET."
        ),
    )
    analyze_parser.add_argument(
        "--sector",
        default=None,
        help="Sector label for this ticker. Used for the 3%% sector heat cap. Omit it and sector heat is not applied.",
    )
    analyze_parser.add_argument(
        "--earnings-date",
        type=_iso_date,
        default=None,
        metavar="YYYY-MM-DD",
        help="Use this report date for this run when the calendars are missing or wrong. Stamped on the plan.",
    )
    analyze_parser.add_argument("--verbose", action="store_true", help="Log to stderr. Stdout stays clean for --json.")
    return parser


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("earnings-date must be YYYY-MM-DD") from exc


def _usd_equity(value: str) -> float:
    try:
        equity = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "equity must be a non-negative finite number of USD. No equity figure was invented."
        ) from exc
    if not math.isfinite(equity) or equity < 0:
        raise argparse.ArgumentTypeError(
            "equity must be a non-negative finite number of USD. No equity figure was invented."
        )
    return equity


def _journal_hint(envelope, path: Path, open_lines: int) -> str | None:
    """Explain old plan lines that block entries. The file is never moved by the CLI."""
    if open_lines == 0 or not envelope.reasons:
        return None
    if envelope.reasons[0].code not in (ReasonCode.MAX_POSITIONS, ReasonCode.HEAT_LIMIT):
        return None
    archive = path.with_name("journal.v0.jsonl")
    return (
        f"Open risk comes from {open_lines} line(s) in {path}. Earlier versions appended every planned "
        "ENTER_LONG there; analyze no longer does, and those lines are plans, not fills. "
        f"If none are real IBKR positions, archive the file yourself:\n  mv \"{path}\" \"{archive}\""
    )


def _sector(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        stream=sys.stderr,
        force=True,
        format="%(levelname)s %(name)s: %(message)s",
    )
    # yfinance logs vendor 404s (for example, no calendar for an ETF) as errors.
    logging.getLogger("yfinance").setLevel(logging.DEBUG if verbose else logging.CRITICAL)


if __name__ == "__main__":
    sys.exit(main())
