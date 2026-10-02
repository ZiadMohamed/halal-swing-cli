# Architecture

Personal cash-long CLI. Not financial advice. Not a Shariah certification. Not a broker.

The screened universe is `~/.swing/universe.txt`. The CLI never places, routes, or stages an order.

## Commands

| Command | Role |
|---|---|
| `swing analyze TICKER` | One ticker. Card by default, `--explain` for gates, `--json` for the envelope |
| `swing buy` / `swing sell` | Append a fill to `book.jsonl` |
| `swing positions` / `swing today` | Open lots, exits due, settled-cash figure |
| `swing review` | Closed-trade R and an unproven label. `--plans` scores cached plans |
| `swing backtest` | Pre-registered variants on a parquet cache. No parameter search |
| `swing doctor` | Keys, paths, SPY freshness, book integrity |

Decisions are `ENTER_LONG` and `NO_TRADE`. `account.mode` is `cash` only.

## Layout

```
src/swing/
  cli.py            argparse and exit codes
  config.py         SwingConfig, config_hash
  home.py           ~/.swing and the one-time copy from Application Support
  book.py           book.jsonl and plans.jsonl
  analyze.py        one-ticker orchestration
  backtest.py       day loop, costs, metrics, Appendix A variants
  doctor.py         local checks
  brain/            indicators, triggers, checklist, rank and slots
  data/             Massive, yfinance, Finnhub, cache, NYSE calendar
  output/           card, explain, JSON schema 2.0.0
```

## Data

Bars: Massive grouped daily for the universe, a throttled per-ticker backfill (5 calls a minute), then yfinance, then `DATA_STALE`. Splits are one list per day. A move of 40% or more without a listed split is `DATA_SUSPECT` via `unexplained_gap`.

Earnings: Finnhub `/calendar/earnings` and the yfinance calendar. The earlier next date wins. More than three sessions of disagreement is `WARN_EARNINGS_DISAGREE`. `--earnings-date` overrides one run and is stamped on the plan. An empty list is not a clear calendar unless Finnhub returned that full window. ETFs skip the earnings gate.

Finnhub premium endpoints are not called. Context.dev is not a dependency.

## What the checklist does today

The live checklist is still the v0 book: three triggers with the mutex, a 1.5×ATR stop, a 2R target, heat and four positions, and the earnings blackout. v1 (trend filter, momentum rank, regime gate, earnings exit, five slots, trail) was measured and not switched on. See [docs/backtests/v1-gate.md](backtests/v1-gate.md). In the 2014 window the random-rank book had the higher Sharpe.

Operator equity, the half-size risk for the first 20 closed fills, and the benchmark ticker are recorded in [docs/decisions/SECTION8_ANSWERS.md](decisions/SECTION8_ANSWERS.md). `account.equity_usd` in `~/.swing/config.toml` is the satellite sleeve only. Those choices do not change the built-in checklist.

`swing backtest` can still run v1 and the Appendix A variants on cached bars.

## Book

`book.jsonl` is append-only buys and sells. Open shares are buys minus sells. A bad line stops the command and names the line. Available cash is equity minus open cost basis minus same-day sale proceeds.

`plans.jsonl` stores `ENTER_LONG` plans, deduped on ticker, signal session, and `config_hash`. A v0 `journal.jsonl` is copied to `journal.v0.jsonl` and imported as plans. It is not imported as fills.

Review prints **unproven** until mean R − 2·SE is above 0 after at least 100 closed trades.

## Locks

- Cash, long equity or ETF, USD.
- No shorts, margin, options, CFDs, futures, or FX.
- No broker library in `uv.lock`.
- No Shariah screen and no certification wording.
- Tests do not open a network connection.
