# halal-swing-cli

This is a personal checklist for cash, long-only trades in US stocks and stock funds, in dollars. A long-only trade means you buy shares. You do not borrow shares to bet on a fall. You type the orders into Interactive Brokers yourself. The program never sends an order.

You already chose the ticker. The program does not decide whether a company is acceptable to you. It answers a narrower question: given the daily prices, do today's rules say buy, and if so at what stop, profit price, and share count?

Use the card as one input to your own decision. It is not an autopilot. If the cash is not there, do not type the buy.

## How a decision is made

1. Load the daily prices for the ticker you typed. The last bar has to be the last finished New York session. A bar with a missing price is dropped.
2. Skip the trade when the next open sits in the earnings window: two sessions before the company report through one session after. A report can jump the price past any stop. A fund has no report, so this check does not apply to it.
3. Look for one of three patterns, in this order. The first match is the name on the card. All three use the same stop and the same profit price.
   - **Volume breakout.** The close (the last price of the day) is above the 50-day average and above the highest high of the prior 20 sessions, and today's volume is at least 1.5 times the average volume of those 20 sessions.
   - **Pullback.** The close is still above the 50-day smoothed line. A smoothed line is an average that weighs recent days more than old days. The day's low tags the 20-day smoothed line, and the close finishes back above it.
   - **Two-day dip.** The close is above the 200-day average, and RSI(2) is below 10. RSI(2) is a 0–100 score of the last two days. A low number means those closes were down days.
4. The stop is 1.5 times the average daily range below the close. The average daily range, ATR(14), is how far the price typically travels in one day, including the overnight gap, smoothed over 14 sessions. The profit price is twice that distance above the close. Twice that distance is called 2R. One R is the distance from the buy to the stop. The share count risks about 1% of the sleeve to that stop, rounded down. The sleeve is the dollars you pass with `--equity` or set in the config. It is the money this checklist manages, not your whole account.

## What it is good at

The card is one decision: buy or no trade, the prices in cents, the share count, the dollars at risk, and the readings behind them. The stop is in that stock's own daily movement, not a percent copied from a different stock. A stop-out is sized at about 1% of the sleeve. The days around a company report are blocked. You still type every order.

## What it is bad at

The three patterns are easy to see on a chart. They are not an edge on their own. In this repo's backtest, with the same stop and the same 2R profit price, the patterns made **+0.133R** a trade. Buying on a random day made **+0.164R**. A random day while the close was above the 200-day average made **+0.142R**. That test is Appendix A of the redesign plan, and it is repeated in [docs/decisions/ALGO_REVIEW_2026-10.md](docs/decisions/ALGO_REVIEW_2026-10.md).

A later book, v1, ranked the names, trailed the stop instead of capping the winner at 2R, and limited each name to 20% of the sleeve. It grew faster than v0 in both test windows (about 13.7% a year versus −9.9% in 2021–2026, and 12.7% versus 5.9% in 2014–2026). It failed the ship rule. In the longer window, ranking those same signals at random had the calmer path: Sharpe 0.95 versus 0.90. Sharpe is yearly growth divided by how bumpy the path was. The live rules stayed on v0. The review has the sources and the numbers.

The share count does not look at cash already tied up. In that backtest the typical buy was about a third of the sleeve, so several buys do not fit in a cash account. The 2R profit price also cuts off the rare very large winner. Published long-only trend tests make their money on those winners, and they hold for months, not days. This checklist does not.

## Install

```bash
brew install uv
git clone https://github.com/ZiadMohamed/halal-swing-cli.git
cd halal-swing-cli
uv tool install --editable .
cp .env.example .env
```

Put `FINNHUB_API_KEY` and `MASSIVE_API_KEY` in `.env`. Doctor requires both free keys. The shell wins over the file. Bars stay on yfinance until you set `SWING_BARS_PROVIDER=massive`. Context.dev is not a dependency.

## ~/.swing

| File | Use |
|---|---|
| `config.toml` | Copy `config/swing.example.toml`. `equity_usd` is the satellite sleeve |
| `.env` | Keys. Not committed. Mode `0600` |
| `book.jsonl` | Buy and sell fills you record. Append-only. Plans are never imported here |
| `plans.jsonl` | Plans from `analyze`, including a v0 journal import. Deduped |
| `cache/bars/` | Daily bars |

## Operator config

The live checklist stays on v0. Built-in `SwingConfig` numbers are unchanged. `~/.swing/config.toml` is the operator file, and it is not in git. The recorded choices are in [docs/decisions/SECTION8_ANSWERS.md](docs/decisions/SECTION8_ANSWERS.md).

- `account.equity_usd` is the satellite sleeve in USD, not total net worth. Start near 20% of total USD equity. The other 80% stays in a screened USD equity ETF held outside this CLI. The plan's examples are SPUS and HLAL. This program does not rank them.
- `risk.per_trade` in code stays `0.01`. In the operator file, set `0.005` until `book.jsonl` has 20 closed real fills, then set it back to `0.01`. Plans are not fills. Change the file by hand. There is no automatic ratchet. Twenty closes are a process check, not proof of an edge.
- `benchmark.symbol` is `"SPUS"`, or the screened core ETF you actually hold, so a later review can compare the sleeve with that core. The live loader does not accept `benchmark.symbol` yet. `swing review` still compares with SPUS. Do not add that key to `config.toml` until the loader accepts it.
- The core ETF stays outside this CLI. The CLI manages the satellite only.
- A v0 `journal.jsonl` is archived and imported into `plans.jsonl` only. Nothing from that file is written into `book.jsonl`. A real fill is a manual `swing buy` after you confirm the shares, price, and date.
- `account.mode` stays `"cash"`. Size from settled cash, not buying power. You type the orders. This program does not send them. The recorded pricing choice for this book's order size is IBKR Pro Tiered. Re-read the schedule in the account portal before relying on it.

## Tickers

There is no `universe.txt`. `swing analyze` takes the one ticker you type. It does not read a list, and doctor does not look for one. This program does not rank a list of tickers. A ranked scan was described in the redesign notes and was never wired, so the file had nothing to feed.

You still supply the screened ticker yourself. Pass the core ETF only when you mean to swing it. SPY is not a holding.

## v1 config surface (not wired)

`swing analyze` stays on the v0 checklist. The values below are the future book. They already match `VARIANTS["v1"]` in the backtest. They are written in `config/v1-surface.example.toml` so the numbers have a file. That file is not loaded. Copying it over `~/.swing/config.toml` makes the CLI reject the config. Do not retune them here. Full notes: [docs/decisions/SECTION8_ANSWERS.md](docs/decisions/SECTION8_ANSWERS.md).

| Key | Value |
|---|---|
| `portfolio.slots` | `5` |
| `portfolio.max_position_frac` | `0.20` |
| `regime.gate` | `true` |
| `regime.symbol` | `"SPY"` |
| `regime.sma` | `200` |
| `trend.sma` | `200` |
| `rank.lookback` | `126` |
| `rank.skip` | `5` |
| `exit.mode` | `"trail"` |
| `exit.trail_atr` | `3.0` |
| `exit.target_r` | `2.0` |
| `entry.cap_atr` | `1.0` |
| `stops.initial_atr` | `1.5` |
| `earnings.min_room_sessions` | `3` |
| `earnings.after_days` | `1` |
| `liquidity.min_price` | `5` |
| `liquidity.min_median_dollar_volume` | `10000000` |

An old `~/Library/Application Support/swing` folder is copied once and left in place.

## Daily workflow (Cairo)

US cash session is 16:30–23:00 Cairo for most of the year, and 15:30–22:00 when only one country is on daylight time.

1. After about 08:00 Cairo, `swing today` lists exits due and open lots.
2. `swing analyze TICKER --equity USD` prints three short sections: BUY or NO TRADE and the one reason, the prices in cents, and the readings behind them. The next open is one line in your timezone (Cairo unless you change it). `--simple` prints that same card. `--explain` adds the gates and the longer buy and sell sentences. `--verbose` adds the config hash and the product note. `--json` prints the full envelope, including the hash and the note.
3. Type the ticket in Interactive Brokers before the open. The CLI does not send it.
4. After the fill, `swing buy TICKER --shares N --price P`. On the way out, `swing sell TICKER --shares N --price P --reason stop|trail|earnings|manual`.
5. Weekly, `swing review` and `swing review --plans`. The book is **unproven** until mean R − 2·SE is above 0 after 100 closed trades.

`swing doctor` requires `FINNHUB_API_KEY` and `MASSIVE_API_KEY`, and it checks SPY freshness and the book. It does not look for a ticker list. A missing Massive key does not block a fresh yfinance bar. The built-in bars provider stays `yfinance`.

## How to use the plan (manual IBKR)

Money is USD. There is no FX conversion.

An `ENTER_LONG` stamp of `checklist_only` means the predetermined rules matched.

**When to buy.** The card says BUY and names the setup (`BO_RVOL`, then `PB_EMA`, then `RSI2_MR`). The fill is the next NYSE open. The planned entry is the signal close, shown in cents. You type the cash long in Interactive Brokers. This CLI does not send the order.

**When to sell.** v0 exits at the stop or the 2R target. Time-stops are not in v0. An SMA(5) exit is not in v0. You type the exit in Interactive Brokers yourself.

## Research data

Daily use does not wait on a paid history file. The optional harness download is Sharadar Prices, full history (SEP). Nasdaq Data Link still aliases that equity-price table as SEP. It is for rerunning the pre-registered variants only. Do not put that key on the live scan path, and do not search parameters on the new file. See [docs/decisions/SECTION8_ANSWERS.md](docs/decisions/SECTION8_ANSWERS.md).

## Tests

```bash
uv run pytest
```
