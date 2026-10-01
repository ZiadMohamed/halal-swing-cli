# Architecture — halal-swing-cli (Chat 1)

Personal local checklist for Ziad Osman. Not financial advice. Not a Shariah certification. Not a broker.

The predetermined checklist (research round 10, prefs 1–12 locked 2026-10-01) is the product. This repository does not invent a new edge and does not invent a fatwa.

## What v0 is

`swing analyze TICKER` prints one decision envelope:

- decision: `ENTER_LONG`, `NO_TRADE`, or `BLOCK`
- when the brain exists: entry, stop, target, size, `next_open`
- reason and warning codes
- disclaimer
- `config_hash`

Product guards still return `BLOCK` before the brain. With bars loaded, the checklist brain returns `ENTER_LONG`, `NO_TRADE`, or stops on a gate. `PIPELINE_NOT_IMPLEMENTED` remains only if something still calls `StubBrain`. The command returns a real envelope either way.

There is no `ENTER_SHORT`. Short, margin, and derivative intents stop at `BLOCK_SHORT`, `BLOCK_MARGIN`, or `BLOCK_DERIVATIVE`.

## Stack

See [ADR 0001](adr/0001-python-uv-and-boundaries.md). Python 3.12, uv, Pydantic, stdlib TOML, stdlib HTTP. Parquet bars are cached under the macOS data root.

## Layout

```
src/swing/
  cli.py            argv, exit codes, logging to stderr
  config.py         locked defaults and TOML load
  hashing.py        config_hash
  codes.py          decision and reason codes (Shariah codes reserved)
  guards.py         cash / long / equity product gate
  analyze.py        orchestration only
  envelope.py       schema 1.1.0
  disclaimer.py
  paths.py          macOS Application Support, Linux fallback
  research/         LiveResearch adapter (Context or skip)
  data/ports.py     BarProvider, EventProvider, CalendarProvider
  brain/            gate order + ChecklistBrain
  output/render.py  text and JSON
  journal/paper.py  append-only paper JSONL
  broker/ibkr.py    IBKR stub, no network
```

## Runtime flow

```
argv
  → load SwingConfig (defaults, optional TOML, SWING_BARS_PROVIDER)
  → load open risk from journal.jsonl (missing file = empty book)
  → product guard (short / margin / derivative)
  → ChecklistBrain.evaluate(ticker, config, market, positions, sector)
  → LiveResearch.enrich(ticker)                    # fail-soft
  → Envelope (checklist fields + data summary + advisory research)
  → append one JSONL line when the decision is ENTER_LONG
  → stdout
```

Exit `0` means an envelope was produced, including `BLOCK` and `NO_TRADE`. Exit `2` means bad usage, an unknown ticker, or a journal line that cannot be read. A missing API key is exit `0` with `WARN_RESEARCH_UNAVAILABLE`.

## Determinism boundary

Checklist math is a pure function of bars, the NYSE calendar, events from the data ports, and the hashed config. Live search is attached after that function returns.

Rules:

- `ChecklistBrain.evaluate` does not take a research client.
- Research warnings are `warnings`, not `reasons`. They do not explain a `NO_TRADE` by themselves.
- `WARN_NEWS` is reserved for a later soft note. It must not change entry, stop, target, size, or next_open.
- A future deterministic halt or earnings blackout may still `NO_TRADE`. That input comes from data ports, not from a headline.
- `config_hash` covers policy only. It does not cover headlines, clock time, or home-directory paths.

`confidence` is `checklist_only` on `ENTER_LONG` and absent otherwise. `ENTER_LONG` also requires `side="long"` and a plan.

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
| `spy_r2` | `0.70` over 60 sessions, effect `warn` |
| bars | `yfinance` or `massive` (never Finnhub) |
| events | `finnhub` |
| `earnings.strict` | `true`, blackout T−2 through T+1 |
| `exdiv.strict` | `false` (ordinary ex-div warns). `block_yield_gte` `0.01` still blocks a large distribution. `strict = true` blocks the ex-div window |
| `output.compact` | `false` |
| journal | `paper_jsonl` |
| `shariah.screen_in_v0` | `false` |
| account | `cash`, `longs_only` |
| clocks | user `Africa/Cairo`, market `America/New_York` |

Frozen checklist parameters from the algorithm pack (not a new claim of edge): ATR(14) × 1.5 stop, target 2R, BO RVOL ≥ 1.5 versus 20-day volume SMA excluding today, close above SMA(50), PB EMA 20/50, RSI2 trend SMA(200). Time-stops (research sketch 5/15/20 sessions) are **not** in config. They were not re-locked.

`account.equity_usd` stays unset until Ziad writes it. Sizing cannot run without it. Chat 3 owns that check.

## Decision codes

Primary decision is `ENTER_LONG`, `NO_TRADE`, or `BLOCK`.

Product blocks used when an intent asks for them: `BLOCK_SHORT`, `BLOCK_MARGIN`, `BLOCK_DERIVATIVE`.

Shariah codes exist on the enum so the schema has a place for them. The v0 analyze path does not emit them and does not call a screen:

- `BLOCK_SHARIAH_SCREEN`
- `BLOCK_SHARIAH_SECTOR`
- `BLOCK_SHARIAH_DATA`
- `BLOCK_SHARIAH_QUESTIONABLE`
- `BLOCK_SHARIAH_OVERRIDE_DENIED`
- `WARN_PURIFICATION`
- `WARN_SHARIAH_STALE`
- `WARN_DIY_SCREEN`
- `WARN_SHARIAH_WEAPONS_POLICY`
- `WARN_SHARIAH_DISAGREEMENT`

Other reserved codes Chat 3 will fill: `WARN_SPY_R2`, `WARN_EXDIV`, `EARNINGS_BLACKOUT`, `SETUP_SUPPRESSED`, `WARN_NEWS`.

The envelope `shariah` object is always `screened: false`, `status: user_supplied`.

## Live research (Context.dev)

Provider interface: `LiveResearch.enrich(ticker) -> ResearchResult`.

| Env | Role |
|---|---|
| `CONTEXT_DEV_API_KEY` | Bearer token for the CLI process. Optional. |
| `CONTEXT_DEV_BASE_URL` | Default `https://api.context.dev/v1`. Must be `https`, or `http` on localhost only. Anything else skips the call with `WARN_RESEARCH_ERROR` and does not send the key. |

Factory behavior:

- `research.enabled = false` → skip, reason `disabled`, no warning (opt-out).
- key missing → skip, reason `missing_api_key`, warning `WARN_RESEARCH_UNAVAILABLE`.
- key set → `POST /web/search` with query `{TICKER} stock news`, `numResults` 10, `freshness` `last_week`, `country` `us`. Timeout 8s. Titles, URLs, and descriptions only (no markdown scrape).
- HTTP, timeout, or bad JSON → `status: error`, warning `WARN_RESEARCH_ERROR`, process continues.

The key is sent only as an `Authorization` header. It is stripped from error text. It is not a config field and not part of `config_hash`.

Context is for runtime stock checks (news / soft context). It is separate from bar vendors and from Finnhub. Missing Context never blocks a checklist that the brain would otherwise complete.

`affects_checklist_math` on the attachment is always `false`.

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

**Chat 3 — Brain.** Done. `ChecklistBrain` walks `PIPELINE_GATES` in order. Mutex is BO_RVOL then PB_EMA then RSI2_MR, one `ENTER_LONG`, losers `SETUP_SUPPRESSED`. High SPY R² is `WARN_SPY_R2` only. Earnings strict blackout is `NO_TRADE`. `confidence` is `checklist_only` on enter. Research is not an argument.

**Chat 4 — Output.** Done. `render_text` shows the decision, reason and warning codes, the plan when present, gate name and status, and the disclaimer on the full view and on `--compact`. `next_open` is printed in `America/New_York` and in `timezone.user` (default `Africa/Cairo`), the same instant. `--compact` stays default off. `--json` is one document and still carries `config_hash`, `shariah.screened=false`, and `research.affects_checklist_math=false`. A headline does not change plan numbers. The renderer does not read or write the journal.

**Chat 5 — Hardening.** Done. `PaperJournal` appends one JSON object per planned `ENTER_LONG` at `journal_path()` and never rewrites earlier lines. The CLI loads that book into `analyze` before the checklist, so heat `0.06`, sector heat `0.03` (only with `--sector` or a stored sector), and `max_concurrent_positions` `4` see prior plans. `risk_fraction` is `size_shares * (entry - stop) / equity_usd`. No `SwingConfig` field was added, so `config_hash` is unchanged. `IbkrBrokerStub` still raises. See `HANDOVER.md` for what v0 does not do yet.

## Out of v0

Live brokers, shorts, conventional margin, options, CFDs, futures, VCP, ORB, multi-ticker scan, Zoya, Norgate, and any certification wording.
