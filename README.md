# halal-swing-cli

Personal cash-long checklist for US equities and ETFs. You type the orders in Interactive Brokers. This program does not send them.

**Not financial advice. Not a Shariah certification.** You supply the screened tickers. `confidence` stays `checklist_only`. That means the rules matched. It is not a claim of edge.

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
| `universe.txt` | At least 20 screened names, target 30–50. Tag ETF rows. Core ETF and SPY stay out |
| `book.jsonl` | Buy and sell fills you record. Append-only |
| `plans.jsonl` | Plans from `analyze`. Deduped |
| `cache/bars/` | Daily bars |

## Operator config

The live checklist stays on v0. Built-in `SwingConfig` numbers are unchanged. `~/.swing/config.toml` is the operator file, and it is not in git. The recorded choices are in [docs/decisions/SECTION8_ANSWERS.md](docs/decisions/SECTION8_ANSWERS.md).

- `account.equity_usd` is the satellite sleeve in USD, not total net worth. Start near 20% of total USD equity. The other 80% stays in a screened USD equity ETF held outside this CLI. The plan's examples are SPUS and HLAL. This program does not rank them.
- `risk.per_trade` in code stays `0.01`. In the operator file, set `0.005` until `book.jsonl` has 20 closed real fills, then set it back to `0.01`. Plans are not fills. Change the file by hand. There is no automatic ratchet. Twenty closes are a process check, not proof of an edge.
- `benchmark.symbol` is `"SPUS"`, or the screened core ETF you actually hold, so a later review can compare the sleeve with that core. The live loader does not accept `benchmark.symbol` yet. `swing review` still compares with SPUS. Do not add that key to `config.toml` until the loader accepts it.
- Keep the core ETF out of `universe.txt`. The CLI manages the satellite only.
- `account.mode` stays `"cash"`. Size from settled cash, not buying power. You type the orders. This program does not send them. The recorded pricing choice for this book's order size is IBKR Pro Tiered. Re-read the schedule in the account portal before relying on it.

## Universe

`~/.swing/universe.txt` should hold at least 20 user-screened USD stocks. The working target is 30–50. One name per line. Tag an ETF only when you have already screened it, as `TICKER ETF`. The live earnings skip still uses vendor instrument type. Analyze does not read that tag yet.

Keep the core ETF out of the file so the CLI does not swing the core. SPY stays out of the file. It is a timing series, not a holding.

Below 20 names, a scan may still run. Doctor labels that list a thin universe. The live checklist has no hard block on the count. Names that fail a later liquidity floor are skipped with a reason. Count names that pass, not only lines in the file. See [docs/decisions/SECTION8_ANSWERS.md](docs/decisions/SECTION8_ANSWERS.md).

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
2. `swing analyze TICKER --equity USD` prints the card. `--explain` adds the gates. `--json` prints the envelope.
3. Type the ticket in Interactive Brokers before the open. The CLI does not send it.
4. After the fill, `swing buy TICKER --shares N --price P`. On the way out, `swing sell TICKER --shares N --price P --reason stop|trail|earnings|manual`.
5. Weekly, `swing review` and `swing review --plans`. The book is **unproven** until mean R − 2·SE is above 0 after 100 closed trades.

`swing doctor` requires `FINNHUB_API_KEY` and `MASSIVE_API_KEY`, and it checks the universe file, SPY freshness, and the book. A missing Massive key does not block a fresh yfinance bar. The built-in bars provider stays `yfinance`.

## How to use the plan (manual IBKR)

Money is USD. There is no FX conversion.

An `ENTER_LONG` stamp of `checklist_only` means the predetermined rules matched.

**When to buy.** The card names the setup (`BO_RVOL`, then `PB_EMA`, then `RSI2_MR`). The fill is the next NYSE open. The planned entry is the signal close. You type the cash long in Interactive Brokers. This CLI does not send the order.

**When to sell.** v0 exits at the stop or the 2R target. Time-stops are not in v0. An SMA(5) exit is not in v0. You type the exit in Interactive Brokers yourself.

## Research data

Daily use does not wait on a paid history file. The optional harness download is Sharadar Prices, full history (SEP). Nasdaq Data Link still aliases that equity-price table as SEP. It is for rerunning the pre-registered variants only. Do not put that key on the live scan path, and do not search parameters on the new file. See [docs/decisions/SECTION8_ANSWERS.md](docs/decisions/SECTION8_ANSWERS.md).

## Tests

```bash
uv run pytest
```
