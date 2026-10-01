"""Terminal entrypoint."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from pydantic import ValidationError

from swing import __version__
from swing.analyze import analyze
from swing.config import load_config
from swing.output.render import render_json, render_text


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command != "analyze":
        parser.print_help(sys.stderr)
        return 2
    _configure_logging(args.verbose)
    try:
        config = load_config(path=args.config)
        compact = bool(args.compact or config.output.compact)
        envelope = analyze(args.ticker, config=config, compact=compact, fetch_market=True)
    except (ValueError, ValidationError, FileNotFoundError) as exc:
        print(exc, file=sys.stderr)
        return 2
    if args.json:
        sys.stdout.write(render_json(envelope))
    else:
        sys.stdout.write(render_text(envelope))
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
        description="Personal cash-long swing checklist. Not financial advice. Not a Shariah certification.",
    )
    analyze_parser.add_argument("ticker", help="US equity ticker you have already screened (example: AAPL)")
    analyze_parser.add_argument("--json", action="store_true", help="Print the decision envelope as JSON")
    analyze_parser.add_argument(
        "--compact",
        action="store_true",
        help="Shorter text. Default off. Still prints the disclaimer.",
    )
    analyze_parser.add_argument("--config", type=Path, help="TOML config file. Overrides discovery.")
    analyze_parser.add_argument("--verbose", action="store_true", help="Log to stderr. Stdout stays clean for --json.")
    return parser


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        stream=sys.stderr,
        force=True,
        format="%(levelname)s %(name)s: %(message)s",
    )


if __name__ == "__main__":
    sys.exit(main())
