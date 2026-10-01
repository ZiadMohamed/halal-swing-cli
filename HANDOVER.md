# v0 complete

Cash-long checklist for Ziad Osman on macOS. `swing analyze TICKER` prints one envelope. A planned `ENTER_LONG` is appended to the paper journal. The next run reads that book, so heat, sector heat, and the four-position cap see prior plans. This is not a Chat 6 build brief.

Not financial advice. Not a Shariah certification. v0 does not screen tickers and does not place orders.

## Run it

```bash
brew install uv
git clone git@github.com:ZiadMohamed/halal-swing-cli.git
cd halal-swing-cli
uv sync
uv run swing analyze --help
```

Copy `config/swing.example.toml` to `~/Library/Application Support/swing/config.toml` (or `./swing.toml`, which is gitignored) and set equity. Sizing refuses the trade while `account.equity_usd` is unset. No equity figure is invented.

```toml
[account]
equity_usd = 100000
```

```bash
uv run swing analyze AAPL
uv run swing analyze AAPL --sector Technology
uv run swing analyze AAPL --json
```

`uv run pytest` stays offline.

## What the journal does

Path: `~/Library/Application Support/swing/journal.jsonl`. `SWING_DATA_DIR` overrides the root. Linux CI uses `$XDG_DATA_HOME/swing` or `~/.local/share/swing`.

One JSON object per line. Append only when the decision is `ENTER_LONG`, after the envelope exists, from the CLI. The renderer does not touch the file. `NO_TRADE` and `BLOCK` write nothing. A second `ENTER_LONG` appends a second line. Lines are never rewritten or deleted.

`size_shares` is copied from the plan. `risk_fraction` is `size_shares * (entry - stop) / equity_usd`. Sector is stored when `--sector` was passed. Blank sectors are not one bucket. A line that is not JSON, or that has no `risk_fraction`, stops the command (exit 2) so heat is not computed from a partial book.

`config_hash` is unchanged. The journal is not a `SwingConfig` field.

`IbkrBrokerStub.place_order` still raises. The error says live trading is out of scope.

## Next, when you want it

These are choices, not a scheduled build.

- **Equity.** The number has to be yours. The example file leaves it commented out on purpose.
- **Bars bake-off.** yfinance is the default and is an unofficial prototype. Massive Basic is already implemented (`SWING_BARS_PROVIDER=massive` plus `MASSIVE_API_KEY`). Switch when the yfinance series is the thing you no longer trust, not before.
- **Massive limits.** Basic daily aggregates are about two years. Paying for Starter is a billing choice. It is not a code default.
- **Optional IBKR.** Live orders stay out until you ask. The stub must keep raising until that version exists.
- **A shrinking book.** v0 treats every journaled plan as still open. Closing a name would be a new append-only record in a later version, not a rewrite of this file.

## Still true

Mutex order, risk 1%, heat 6% / 3%, max 4 positions, RSI(2) below 10, and SPY R² warn at 0.70 over 60 sessions are locked. Research does not change checklist math. There is no Shariah screen and no fatwa in this repo. Time-stops are not in config. Indicator formulas and gate order are unchanged. Clocks stay `America/New_York` and `Africa/Cairo`, including winter `+02:00` in Cairo.
