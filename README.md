# halal-swing-cli

Personal local checklist for Ziad Osman. A ticker goes in. A swing decision envelope comes out: entry, stop, target, size, next NYSE open, and reason codes.

**Not financial advice. Not a Shariah certification.** This is a personal rule checklist. It does not predict returns, and it does not certify compliance with AAOIFI, SC Malaysia, S&P Shariah, DJIM, or any other standard.

Cash account, long equity only. No shorts, no conventional margin, no options, CFDs, or futures. You supply pre-screened tickers. v0 does not call Zoya and does not screen halal status. You own compliance, purification, and any scholar consult.

An `ENTER_LONG` stamps `confidence: "checklist_only"`. That means the predetermined rules matched. It is not a claim of edge.

`swing analyze` runs the checklist brain. A match can print `ENTER_LONG` with entry, stop, target, size, and the next NYSE open. Anything else stays `NO_TRADE` or `BLOCK`, with the disclaimer and config hash on every envelope. Set `account.equity_usd` or size is refused. Each planned `ENTER_LONG` is appended to the paper journal, and the next run counts that open risk toward the 6% heat cap, the 3% sector cap, and the four-position limit.

## macOS setup

The daily-driver is macOS, Apple Silicon and Intel. The commands are the same. [uv](https://docs.astral.sh/uv/) installs the matching CPython for you.

```bash
# Homebrew, or the uv installer (works on Apple Silicon and Intel):
brew install uv
# curl -LsSf https://astral.sh/uv/install.sh | sh

git clone git@github.com:ZiadMohamed/halal-swing-cli.git
cd halal-swing-cli
uv sync
uv run swing analyze --help
uv run swing analyze AAPL
uv run swing analyze AAPL --json
uv run swing analyze AAPL --sector Technology
```

`uv sync` creates `.venv` and installs the locked dependencies from `uv.lock`. You do not need a system Python beyond what uv downloads (3.12).

Config and data on macOS live under:

`~/Library/Application Support/swing/`

| Path | Use |
|---|---|
| `config.toml` | Optional. Copy `config/swing.example.toml` |
| `cache/bars/` | Parquet daily bars. Split-adjusted OHLC plus a corp-action suspect flag |
| `journal.jsonl` | Append-only paper journal of planned `ENTER_LONG` lines |

A `swing.toml` in the current directory is also read, and it is gitignored so account size does not get committed. `SWING_CONFIG` or `--config` overrides discovery.

Linux is a fallback for CI and agents only. On Linux the data root is `$XDG_DATA_HOME/swing` or `~/.local/share/swing`. Do not treat that layout as the supported install.

## What analyze prints

`swing analyze AAPL` prints one envelope. The decision is `ENTER_LONG`, `NO_TRADE`, or `BLOCK`. Reasons name the gate that stopped the checklist (`NO_MARKET_DATA`, `EARNINGS_BLACKOUT`, `EQUITY_UNSET`, `HEAT_LIMIT`, `MAX_POSITIONS`, and the other codes in `src/swing/codes.py`). The text view shows that decision, the reason and warning codes, the plan when one exists (setup, entry, stop, target, size, next open), each gate name and status, and the disclaimer. `--compact` is off unless you pass it; the compact view is shorter and still includes those fields and the disclaimer. The next open is printed in `America/New_York` and again in `timezone.user` (`Africa/Cairo` unless you change it). `--json` prints the envelope (schema `1.1.0`) and nothing else on stdout. `stage` is `skeleton`, `partial`, or `checklist`. The text says the brain has not run only when every gate is still `not_run`.

Exit `0` means an envelope was produced, including `BLOCK` and `NO_TRADE`. Exit `2` means bad usage, a bad ticker, a missing config path, or a journal line that is not valid JSON.

## Paper journal

On macOS the file is `~/Library/Application Support/swing/journal.jsonl`. `SWING_DATA_DIR` overrides that root. The CLI creates the file on the first planned entry. `NO_TRADE` and `BLOCK` do not write a line and do not rewrite earlier ones.

A line is one JSON object. `size_shares` is copied from the plan. `risk_fraction` is `size_shares * (entry - stop) / equity_usd`, using the equity in config. If equity is unset, nothing is invented and nothing is journaled.

Every line stays open risk. v0 does not delete or rewrite lines, so the book only grows. Four open plans block the next entry (`MAX_POSITIONS`). Prior risk plus 1% of equity above 6% blocks with `HEAT_LIMIT`.

`--sector` is optional. Pass it when you know the ticker's sector and the 3% sector cap should apply. A blank sector is not lumped into an unknown bucket. There is no sector vendor in v0.

Put equity in the TOML you actually load (`--config`, `./swing.toml`, or `~/Library/Application Support/swing/config.toml`):

```toml
[account]
equity_usd = 100000
```

`config/swing.example.toml` shows the locked defaults. The example leaves equity commented out so a fresh hash still matches the built-in config.

## Environment variables

None are required to print an envelope.

| Variable | Required | Role |
|---|---|---|
| `CONTEXT_DEV_API_KEY` | no | Live news search at analyze time. Bearer token for `POST /web/search`. Not an OHLC source. |
| `CONTEXT_DEV_BASE_URL` | no | Default `https://api.context.dev/v1`. `https` only, except `http` on localhost |
| `FINNHUB_API_KEY` | no | Earnings and dividend calendars only. Never bars. Missing key is a typed data error, not a crash |
| `MASSIVE_API_KEY` | only if `bars_provider` is `massive` | Bars from Massive Basic. Sent as `Authorization: Bearer`, not in the URL |
| `SWING_BARS_PROVIDER` | no | `yfinance` (default) or `massive` |
| `SWING_CONFIG` | no | TOML file path |
| `SWING_DATA_DIR` | no | Overrides the data root. If `config.toml` is inside it, that file is used unless `--config` or `SWING_CONFIG` is set |

If `CONTEXT_DEV_API_KEY` is missing, analyze adds `WARN_RESEARCH_UNAVAILABLE` and continues. Context headlines are advisory. They do not change entry, stop, target, size, or the decision the checklist produces. Set `research.enabled = false` in TOML to skip the warning on purpose.

The key stays in the environment. It is not written into config, logs, or `config_hash`.

## Locked defaults

Prefs 1–12 are the built-in config. Details and the hash rule are in [docs/architecture.md](docs/architecture.md). The short version:

- Risk 1% of equity per trade
- Setups `BO_RVOL`, `PB_EMA`, `RSI2_MR`, mutex BO then PB then RSI2
- RSI(2) below 10 for the mean-reversion setup
- Heat total at most 6%, sector at most 3%, at most 4 open positions
- SPY R² at or above 0.70 over 60 sessions warns only
- Earnings blackout is strict (T−2 through T+1). Ordinary ex-div warns. A distribution at or above 1% of price still blocks
- Bars: yfinance prototype or Massive. Events: Finnhub
- Paper JSONL journal of planned entries. No live broker

`config/swing.example.toml` matches those defaults. The hash of a run is SHA-256 of the canonical config JSON, so a policy edit is visible on the envelope.

## Tests

```bash
uv run pytest
```

## Layout

Architecture and the decision to stay on Python + uv: [docs/architecture.md](docs/architecture.md), [docs/adr/0001-python-uv-and-boundaries.md](docs/adr/0001-python-uv-and-boundaries.md).

v0 is complete for cash longs once equity is set. Later choices (a bars bake-off, Massive when the free limit hurts, optional IBKR) are noted in [HANDOVER.md](HANDOVER.md).
