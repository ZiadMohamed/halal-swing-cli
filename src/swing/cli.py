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
    if args.command == "backtest":
        return _backtest(args)
    if args.command == "doctor":
        return _doctor()
    if args.command in {"buy", "sell", "positions", "today", "review"}:
        try:
            return _portfolio(args)
        except (ValueError, ValidationError, FileNotFoundError) as exc:
            print(exc, file=sys.stderr)
            return 2
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
    _record_plan(envelope, args)
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
    backtest = sub.add_parser("backtest", help="Run one pre-registered variant on cached bars")
    backtest.add_argument("--variant", default="D2", help="Appendix A name: A, B, C, M, D2, I, J, K, L, H, E, G, I_moo, I_cap")
    backtest.add_argument("--from", dest="start", default="2021-01-04")
    backtest.add_argument("--to", dest="end", default="2026-09-30")
    backtest.add_argument("--cache", type=Path, help="Parquet cache directory. No network.")
    buy = sub.add_parser("buy", help="Append a buy fill. Does not send an order.")
    buy.add_argument("ticker")
    buy.add_argument("--shares", type=int, required=True)
    buy.add_argument("--price", type=float, required=True)
    buy.add_argument("--date", default=None)
    buy.add_argument("--stop", type=float, default=None)
    buy.add_argument("--trail", type=float, default=None)
    buy.add_argument("--exit-by", dest="exit_by", default=None)
    sell = sub.add_parser("sell", help="Append a sell fill. Does not send an order.")
    sell.add_argument("ticker")
    sell.add_argument("--shares", type=int, required=True)
    sell.add_argument("--price", type=float, required=True)
    sell.add_argument("--date", default=None)
    sell.add_argument("--reason", default="manual", choices=["stop", "trail", "earnings", "manual"])
    sub.add_parser("positions", help="Open lots from book.jsonl")
    sub.add_parser("today", help="Exits due and open capacity. Does not download.")
    review = sub.add_parser("review", help="Closed trades and forward-scored plans")
    review.add_argument("--plans", action="store_true")
    sub.add_parser("doctor", help="Check keys, cache, universe, and the book. May call vendors.")
    return parser


def _live_probe(name: str, endpoint: str) -> None:
    import os
    from datetime import timedelta

    key = os.environ.get(name, "").strip()
    if name == "FINNHUB_API_KEY":
        from swing.data.finnhub import FinnhubEvents

        FinnhubEvents(api_key=key).earnings_calendar("AAPL")
        return
    if name == "MASSIVE_API_KEY":
        from swing.data.http import get_json

        day = date.today() - timedelta(days=7)
        url = f"https://api.massive.com{endpoint}/locale/us/market/stocks/{day.isoformat()}?adjusted=true"
        get_json(url, {"Authorization": f"Bearer {key}"})
    del endpoint


def _doctor() -> int:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from swing.data.cache import read_bars
    from swing.data.calendar import NyseCalendar
    from swing.doctor import default_home, render_findings, run_doctor

    home = default_home()
    cache = home / "cache" / "bars"
    series = read_bars(cache, "SPY") if cache.is_dir() else None
    last = None
    try:
        last = NyseCalendar().last_completed_session(datetime.now(ZoneInfo("America/New_York")))
    except Exception:
        last = None
    spy_session = None if series is None or not series.bars else series.bars[-1].session
    findings = run_doctor(
        env=dict(__import__("os").environ),
        home=home,
        cwd=Path.cwd(),
        today=datetime.now().date(),
        last_session=last,
        spy_session=spy_session,
        probe=_live_probe,
    )
    sys.stdout.write(render_findings(findings))
    return 0 if all(item.ok for item in findings) else 1


def _home() -> Path:
    from swing.home import swing_home

    return swing_home()


def _record_plan(envelope, args) -> None:
    from swing.book import append_plan, block_if_open, book_path, import_v0_journal, load_book, plans_path

    root = _home()
    import_v0_journal(root / "journal.jsonl", plans_path(root), root / "journal.v0.jsonl")
    if envelope.decision.value != "ENTER_LONG" or envelope.plan is None:
        return
    _events, lots = load_book(book_path(root))
    if block_if_open(envelope.ticker, lots):
        print(f"{envelope.ticker} is already open. No new plan was written.", file=sys.stderr)
        return
    session = envelope.plan.next_open[:10]
    append_plan(
        plans_path(root),
        {
            "ticker": envelope.ticker,
            "signal_session": session,
            "config_hash": envelope.config_hash,
            "entry": envelope.plan.entry,
            "stop": envelope.plan.stop,
            "target": envelope.plan.target,
            "size_shares": envelope.plan.size_shares,
            "earnings_date": envelope.plan.earnings_date,
        },
    )


def _portfolio(args) -> int:
    from swing.book import (
        append_buy,
        append_sell,
        available_cash,
        book_path,
        closed_trades,
        load_book,
        load_plans,
        parse_cli_date,
        plans_path,
        review_summary,
        score_plan,
    )
    from swing.data.cache import read_bars

    root = _home()
    path = book_path(root)
    if args.command == "buy":
        append_buy(
            path,
            ticker=args.ticker,
            shares=args.shares,
            price=args.price,
            day=parse_cli_date(args.date),
            stop=args.stop,
            trail_amount=args.trail,
            exit_by=args.exit_by,
        )
        print(f"Recorded buy {args.ticker.upper()} {args.shares} @ {args.price}. This did not send an order.")
        return 0
    if args.command == "sell":
        append_sell(
            path,
            ticker=args.ticker,
            shares=args.shares,
            price=args.price,
            day=parse_cli_date(args.date),
            reason=args.reason,
        )
        print(f"Recorded sell {args.ticker.upper()} {args.shares} @ {args.price}. This did not send an order.")
        return 0
    events, lots = load_book(path)
    if args.command == "positions":
        _print_positions(lots, events)
        return 0
    if args.command == "today":
        today = parse_cli_date(None)
        due = [lot for lot in lots if lot.exit_by == today.isoformat()]
        print(f"Exits due {today.isoformat()}: {len(due)}")
        for lot in due:
            print(f"  MOC {lot.ticker} {lot.shares} shares  exit_by {lot.exit_by}")
        _print_positions(lots, events)
        universe = root / "universe.txt"
        if not universe.is_file():
            print(f"No universe file at {universe}. Ranked entries need that list.")
        return 0
    trades = closed_trades(events)
    summary = review_summary(trades)
    _print_review(summary)
    cache = root / "cache" / "bars"
    spus = read_bars(cache, "SPUS") if cache.is_dir() else None
    if spus is not None and trades:
        from swing.book import satellite_vs_benchmark

        satellite, benchmark = satellite_vs_benchmark(trades, spus.bars)
        bench = "unavailable" if benchmark is None else f"{benchmark:.2%}"
        sat = "unavailable" if satellite is None else f"{satellite:.2%}"
        print(f"satellite {sat}  SPUS {bench}")
    if args.plans:
        cache = root / "cache" / "bars"
        for plan in load_plans(plans_path(root)):
            series = read_bars(cache, plan.ticker) if cache.is_dir() else None
            scored = None if series is None else score_plan(plan.payload, series.bars)
            text = "not scored" if scored is None else f"R {scored:.3f}"
            print(f"plan {plan.ticker} {plan.signal_session} {text}")
    return 0


def _print_positions(lots, events) -> None:
    from swing.book import available_cash
    from swing.config import load_config

    if not lots:
        print("No open lots.")
    for lot in lots:
        risk = None if lot.stop is None else lot.price - lot.stop
        print(
            f"{lot.ticker}  {lot.shares} shares  cost {lot.price}  "
            f"stop {lot.stop}  exit_by {lot.exit_by or '-'}  "
            f"risk/share {risk if risk is not None else '-'}"
        )
    try:
        equity = load_config().account.equity_usd
    except (ValueError, FileNotFoundError):
        equity = None
    if equity is not None:
        print(f"available cash {available_cash(equity, lots, events, parse_today())}")


def parse_today():
    from swing.book import parse_cli_date

    return parse_cli_date(None)


def _print_review(summary: dict) -> None:
    if summary["n"] == 0:
        print("No closed trades with a stop. unproven")
        return
    print(
        f"closed {summary['n']}  mean R {summary['mean_r']:.3f} ± {summary['se']:.3f}  "
        f"win {summary['win_rate']:.0%}  avg hold {summary['avg_hold']:.1f} days  {summary['label']}"
    )
    print("The book is unproven until mean R − 2·SE is above 0 after 100 closed trades.")


def _backtest(args) -> int:
    from swing.backtest import VARIANTS, run_backtest
    from swing.data.cache import read_bars

    variant = VARIANTS.get(args.variant)
    if variant is None:
        print(f"Unknown variant {args.variant}.", file=sys.stderr)
        return 2
    cache = args.cache
    if cache is None or not cache.is_dir():
        print("backtest needs --cache of parquet bars. It does not download.", file=sys.stderr)
        return 2
    panels = {}
    for path in sorted(cache.glob("*.parquet")):
        series = read_bars(cache, path.stem)
        if series is not None and series.bars:
            panels[series.ticker] = series.bars
    spy = panels.pop("SPY", None)
    spus = panels.pop("SPUS", None)
    if not panels:
        print("No ticker parquet files in the cache.", file=sys.stderr)
        return 2
    result = run_backtest(
        panels,
        variant=variant,
        start=date.fromisoformat(args.start),
        end=date.fromisoformat(args.end),
        spy=spy,
        benchmarks={name: bars for name, bars in (("SPY", spy), ("SPUS", spus)) if bars is not None},
    )
    metrics = result.metrics
    print(
        f"{result.variant}  CAGR {metrics.cagr:.2%}  maxDD {metrics.max_dd:.2%}  "
        f"Sharpe {metrics.sharpe:.2f}  trades {metrics.trades}  "
        f"meanR {metrics.mean_r:.3f} ± {metrics.se_r:.3f}"
    )
    for name, bench in result.benchmarks.items():
        print(f"{name} buy-hold  CAGR {bench.cagr:.2%}")
    return 0


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
