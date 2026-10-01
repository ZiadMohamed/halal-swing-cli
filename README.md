# halal-swing-cli

Personal local checklist for Ziad Osman. A ticker goes in. A swing decision envelope comes out: entry, stop, target, size, next NYSE open, and reason codes — once the later milestones land.

**Not financial advice. Not a Shariah certification.** This is a personal rule checklist. It does not predict returns, and it does not certify compliance with AAOIFI, SC Malaysia, S&P Shariah, DJIM, or any other standard.

Cash account, long equity only. No shorts, no conventional margin, no options, CFDs, or futures. You supply pre-screened tickers. v0 does not call Zoya and does not screen halal status. You own compliance, purification, and any scholar consult.

Every future `ENTER_LONG` stamps `confidence: "checklist_only"`. That means the predetermined rules matched. It is not a claim of edge.

Chat 1 is the skeleton. `swing analyze` runs, prints the disclaimer and a config hash, and returns `NO_TRADE` because bars and the checklist brain are not installed yet.

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
```

`uv sync` creates `.venv` and installs the locked dependencies from `uv.lock`. You do not need a system Python beyond what uv downloads (3.12).

Config and data on macOS live under:

`~/Library/Application Support/swing/`

| Path | Use |
|---|---|
| `config.toml` | Optional. Copy `config/swing.example.toml` |
| `cache/bars/` | Parquet bars (Chat 2, not written yet) |
| `journal.jsonl` | Paper journal (Chat 5, not written yet) |

A `swing.toml` in the current directory is also read, and it is gitignored so account size does not get committed. `SWING_CONFIG` or `--config` overrides discovery.

Linux is a fallback for CI and agents only. On Linux the data root is `$XDG_DATA_HOME/swing` or `~/.local/share/swing`. Do not treat that layout as the supported install.

## What the skeleton prints

`swing analyze AAPL` prints `NO_TRADE`, reason `PIPELINE_NOT_IMPLEMENTED`, the disclaimer, and `config_hash`. `--compact` is off unless you pass it. `--json` prints the envelope (schema `1.1.0`) and nothing else on stdout.

Exit `0` means an envelope was produced, including `BLOCK` and `NO_TRADE`. Exit `2` means bad usage, a bad ticker, or a missing config path.

## Environment variables

None are required for the skeleton.

| Variable | Required | Role |
|---|---|---|
| `CONTEXT_DEV_API_KEY` | no | Live news search at analyze time. Bearer token for `POST /web/search`. Not an OHLC source. |
| `CONTEXT_DEV_BASE_URL` | no | Default `https://api.context.dev/v1`. `https` only, except `http` on localhost |
| `FINNHUB_API_KEY` | Chat 2 | Earnings and dividend calendars only. Never bars. |
| `MASSIVE_API_KEY` | Chat 2 | Bars when `bars_provider` is `massive` |
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
- Paper JSONL journal later. No live broker

`config/swing.example.toml` matches those defaults. The hash of a run is SHA-256 of the canonical config JSON, so a policy edit is visible on the envelope.

## Tests

```bash
uv run pytest
```

## Layout

Architecture and the decision to stay on Python + uv: [docs/architecture.md](docs/architecture.md), [docs/adr/0001-python-uv-and-boundaries.md](docs/adr/0001-python-uv-and-boundaries.md).

Next milestone (bars, Finnhub events, Parquet, NYSE calendar): [HANDOVER.md](HANDOVER.md).
