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

Put `FINNHUB_API_KEY` and `MASSIVE_API_KEY` in `.env` if you have them. The shell wins over the file.

## ~/.swing

| File | Use |
|---|---|
| `config.toml` | Copy `config/swing.example.toml` and set `equity_usd` |
| `.env` | Keys. Not committed |
| `universe.txt` | One screened ticker per line |
| `book.jsonl` | Buy and sell fills you record. Append-only |
| `plans.jsonl` | Plans from `analyze`. Deduped |
| `cache/bars/` | Daily bars |

An old `~/Library/Application Support/swing` folder is copied once and left in place.

## Daily workflow (Cairo)

US cash session is 16:30–23:00 Cairo for most of the year, and 15:30–22:00 when only one country is on daylight time.

1. After about 08:00 Cairo, `swing today` lists exits due and open lots.
2. `swing analyze TICKER --equity USD` prints the card. `--explain` adds the gates. `--json` prints the envelope.
3. Type the ticket in Interactive Brokers before the open. The CLI does not send it.
4. After the fill, `swing buy TICKER --shares N --price P`. On the way out, `swing sell TICKER --shares N --price P --reason stop|trail|earnings|manual`.
5. Weekly, `swing review` and `swing review --plans`. The book is **unproven** until mean R − 2·SE is above 0 after 100 closed trades.

`swing doctor` checks keys, the universe file, SPY freshness, and the book.

## How to use the plan (manual IBKR)

Money is USD. There is no FX conversion.

An `ENTER_LONG` stamp of `checklist_only` means the predetermined rules matched.

**When to buy.** The card names the setup (`BO_RVOL`, then `PB_EMA`, then `RSI2_MR`). The fill is the next NYSE open. The planned entry is the signal close. You type the cash long in Interactive Brokers. This CLI does not send the order.

**When to sell.** v0 exits at the stop or the 2R target. Time-stops are not in v0. An SMA(5) exit is not in v0. You type the exit in Interactive Brokers yourself.

## Tests

```bash
uv run pytest
```
