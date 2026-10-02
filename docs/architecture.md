# Architecture — halal-swing-cli (Chat 1)

Personal local checklist for Ziad Osman. Not financial advice. Not a Shariah certification. Not a broker.

The predetermined checklist (research round 10, prefs 1–12 locked 2026-10-01) is the product. This repository does not invent a new edge and does not invent a fatwa.

## What v0 is

`swing analyze TICKER` prints one decision envelope:

- decision: `ENTER_LONG` or `NO_TRADE`
- when the brain exists: entry, stop, target, size, `next_open`
- reason and warning codes
- disclaimer
- `config_hash`

With bars loaded, the checklist brain returns `ENTER_LONG` or `NO_TRADE`. `account.mode` is `cash` only, so a margin config is rejected when the file loads.

There is no `ENTER_SHORT`. There is no broker library and no order path.

## Stack

See [ADR 0001](adr/0001-python-uv-and-boundaries.md). Python 3.12, uv, Pydantic, stdlib TOML, stdlib HTTP. Parquet bars are cached under the macOS data root.

## Layout

```
src/swing/
  cli.py            argv, exit codes, logging to stderr
  config.py         locked defaults and TOML load
  hashing.py        config_hash
  codes.py          ENTER_LONG and NO_TRADE, plus reason codes
  analyze.py        orchestration only
  envelope.py       schema 2.0.0 (`instructions` is null unless ENTER_LONG)
  disclaimer.py
  paths.py          macOS Application Support, Linux fallback
  brain/            gate order + ChecklistBrain
  output/render.py  action card, --explain, and JSON
  journal/paper.py  append-only paper JSONL
```

## Runtime flow

```
argv
  → load SwingConfig (defaults, optional TOML, SWING_BARS_PROVIDER)
  → load open risk from journal.jsonl (missing file = empty book)
  → ChecklistBrain.evaluate(ticker, config, market, positions, sector)
  → Envelope (checklist fields + data summary)
  → stdout
```

`analyze` does not append to the journal. Exit `0` means an envelope was produced, including `NO_TRADE`. Exit `2` means bad usage, an unknown ticker, a config that is not cash, or a journal line that cannot be read.

## Determinism boundary

Checklist math is a pure function of bars, the NYSE calendar, events, and the hashed config. News and search results are not inputs.

Rules:

- `ChecklistBrain.evaluate` does not take a research client.
- `config_hash` covers policy only. It does not cover clock time or home-directory paths.

`confidence` is `checklist_only` on `ENTER_LONG` and absent otherwise. `ENTER_LONG` also requires `side="long"` and a plan.

On `ENTER_LONG`, `instructions` carries `buy`, `sell`, and `currency` = `USD`. The envelope schema is `2.0.0`. The default text is the action card. `--explain` prints the gates. Prices are USD. There is no FX conversion. The CLI does not send the order: you type the cash long in Interactive Brokers.

## Config

Defaults live in code so a fresh clone runs with no file. Optional overrides:

1. `--config PATH`
2. `SWING_CONFIG`
3. `./swing.toml` (gitignored; local only)
4. `$SWING_DATA_DIR/config.toml` when that variable is set and the file exists
5. macOS: `~/Library/Application Support/swing/config.toml`
6. other OS: `$XDG_CONFIG_HOME/swing/config.toml` or `~/.config/swing/config.toml`

`config/swing.example.toml` mirrors the locked defaults. Copy it; the CLI does not read it unless you point at it.

`config_hash` is SHA-256 of UTF-8 JSON: `sort_keys`, separators `(',', ':')`, `ensure_ascii`. The payload is `SwingConfig.model_dump(mode="json")`. No secrets belong in that model.

Locked policy (prefs 1–12):

| Key | Value |
|---|---|
| `risk.per_trade` | `0.01` |
| setups | `BO_RVOL`, `PB_EMA`, `RSI2_MR` |
| mutex | BO > PB > RSI2 |
| `setups.rsi2_mr.rsi_max` | `10` (enter when RSI(2) is below this) |
| heat | total `0.06`, sector `0.03` |
| `max_concurrent_positions` | `4` |
| bars | `yfinance` or `massive` (never Finnhub) |
| events | `finnhub` |
| `earnings.strict` | `true`, blackout T−2 through T+1 |
| `exdiv.strict` | `false` (ordinary ex-div warns). `block_yield_gte` `0.01` still blocks a large distribution. `strict = true` blocks the ex-div window |
| journal | `paper_jsonl` |
| `shariah.screen_in_v0` | `false` |
| account | `cash`, `longs_only` |
| clocks | user `Africa/Cairo`, market `America/New_York` |

Frozen checklist parameters from the algorithm pack (not a new claim of edge): ATR(14) × 1.5 stop, target 2R, BO RVOL ≥ 1.5 versus 20-day volume SMA excluding today, close above SMA(50), PB EMA 20/50, RSI2 trend SMA(200). Time-stops (research sketch 5/15/20 sessions) are **not** in config. They were not re-locked.

`account.equity_usd` stays unset until Ziad writes it. Sizing cannot run without it. `swing analyze --equity USD` overrides that value for one run, sizes and journals from the override, and leaves `config_hash` as the hash of the file. The envelope stamps the equity that was used. With neither the flag nor the TOML value set, the decision is `NO_TRADE` / `EQUITY_UNSET`.

## Decision codes

Primary decision is `ENTER_LONG` or `NO_TRADE`. There is no `BLOCK` decision and no `ENTER_SHORT`. Margin is rejected when config loads (`account.mode` is `cash` only).

The envelope `shariah` object is always `screened: false`, `status: user_supplied`. The CLI does not screen and does not certify.

## News

Context.dev is not part of this CLI. Headlines do not change entry, stop, target, size, or the decision.

## macOS run target

Install and daily use are documented for macOS. uv provides CPython for both arm64 and x86_64, so the commands match.

Data and config root on macOS:

`~/Library/Application Support/swing/`

- `config.toml` optional
- `cache/bars/` Parquet (Chat 2)
- `journal.jsonl` append-only planned `ENTER_LONG` lines

`SWING_DATA_DIR` overrides the root. On Linux (CI, this agent) the fallback is `$XDG_DATA_HOME/swing` or `~/.local/share/swing`. That fallback is not the product target.

## How later chats plug in

**Chat 2 — Data.** Done. `load_market_data` returns `MarketData`: split-adjusted bars (yfinance or Massive), a `corp_action_suspect` flag, Finnhub earnings and dividend events, and `next_open` from the NYSE calendar. Parquet lives under `bars_cache_dir()`. The analyze envelope copies a summary onto `data`. Finnhub does not serve OHLC.

**Chat 3 — Brain.** `ChecklistBrain` walks `PIPELINE_GATES` in order. Mutex is BO_RVOL then PB_EMA then RSI2_MR, one `ENTER_LONG`, losers `SETUP_SUPPRESSED`. Earnings strict blackout is `NO_TRADE`. `confidence` is `checklist_only` on enter.

**Chat 4 — Output.** The default text is the action card. `--explain` adds gates. `--json` is one document and carries `config_hash` and `shariah.screened=false`. The renderer does not read or write the journal.

**Chat 5 — Hardening.** `PaperJournal` can append one JSON object per planned `ENTER_LONG` and never rewrites earlier lines. `analyze` no longer appends. The CLI still loads that book into `analyze` before the checklist, so heat `0.06`, sector heat `0.03` (only with `--sector` or a stored sector), and `max_concurrent_positions` `4` see prior plans. `risk_fraction` is `size_shares * (entry - stop) / equity_usd`.

## Out of v0

Live brokers, shorts, conventional margin, options, CFDs, futures, VCP, ORB, multi-ticker scan, Zoya, Norgate, and any certification wording.
