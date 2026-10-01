# Handover — Chat 2 (Data)

Chat 1 shipped a runnable skeleton. Your job is market data only: bars, events, the NYSE calendar, and a Parquet cache. Do not implement setups, sizing, or the paper journal. Those are Chats 3 and 5.

Read [docs/architecture.md](docs/architecture.md) before editing. The product locks are already in `SwingConfig`. Do not invent a fatwa, a Shariah screen, or a trading edge.

## What exists

- Installable CLI: `uv run swing analyze --help` and `uv run swing analyze TICKER`
- `swing analyze` returns envelope schema `1.1.0` with disclaimer, `config_hash`, and `NO_TRADE` / `PIPELINE_NOT_IMPLEMENTED`
- Locked defaults in `src/swing/config.py` and `config/swing.example.toml`
- `config_hash()` in `src/swing/hashing.py` (SHA-256 of sorted compact JSON). Do not change the encoding
- Product guards in `src/swing/guards.py`: short → `BLOCK_SHORT`, margin → `BLOCK_MARGIN`, option/CFD/future → `BLOCK_DERIVATIVE`. There is no `ENTER_SHORT`
- Shariah reason codes exist on `ReasonCode` and in `SHARIAH_REASON_CODES`. v0 analyze must not emit them and must not call Zoya
- Live research adapter: `build_live_research()` → Context `POST /web/search` or a skip. Missing `CONTEXT_DEV_API_KEY` warns and continues. `affects_checklist_math` is fixed `false`
- Brain call has no research argument (`StubBrain.evaluate(ticker, config)`). Keep it that way
- `analyze` copies `ChecklistResult.confidence`, `side`, and `plan` onto the envelope. `ENTER_LONG` still fails validation without `confidence="checklist_only"`, `side="long"`, and a plan. `StubBrain` leaves those empty. Set them on `ChecklistResult` in Chat 3; do not hardcode them in the orchestrator again
- macOS paths: `default_data_dir()`, `bars_cache_dir()`, `journal_path()` in `src/swing/paths.py`
- Ports with no vendors behind them: `src/swing/data/ports.py`
- `PaperJournal.append` and `IbkrBrokerStub.place_order` raise `NotImplementedError` on purpose

`stage` on the envelope is the literal `"skeleton"`. Widen that type when a later chat changes the stage. Do not flip it to look finished while the brain is still the stub.

Tests: `uv run pytest` (35 passing on Chat 1).

## What is stubbed

| Piece | Where | Behavior now |
|---|---|---|
| Bars | `UnimplementedBars` | Raises |
| Finnhub events | `UnimplementedEvents` | Raises |
| NYSE calendar | `UnimplementedCalendar` | Raises |
| Checklist | `StubBrain` | `NO_TRADE`, every gate `not_run` |
| Text/JSON polish, Cairo clock | `output/render.py` | Disclaimer, hash, gates. Chat 4 |
| Paper JSONL | `journal/paper.py` | Raises. Chat 5 |
| IBKR | `broker/ibkr.py` | Raises. Stays unwired |

`analyze()` does not call the data ports. After your providers exist, you may attach a data section, but the decision stays `NO_TRADE` until Chat 3 replaces `StubBrain`. Do not compute RSI, ATR, or position size.

## Exact next steps

1. Add dependencies with uv and commit `uv.lock`. Expected: `yfinance` for the prototype, `pyarrow` for Parquet. Add an HTTP client only if the stdlib client in `research/context_client.py` is a poor fit for Massive. Keep the CLI installable with `uv sync` on macOS (arm64 and x86_64).
2. Implement `BarProvider.fetch_daily(ticker, lookback_sessions)` twice:
   - `yfinance` when `data.bars_provider` is `yfinance` (the default).
   - Massive Basic when it is `massive`, using `MASSIVE_API_KEY`.
   - `SWING_BARS_PROVIDER` already overrides the config key in `load_config`.
   - Reject any attempt to select Finnhub as a bars provider. The schema already does this. Do not add a candle call.
3. Cache daily bars as Parquet under `bars_cache_dir()` (`~/Library/Application Support/swing/cache/bars` on macOS). Store split-adjusted OHLC used for indicators, and keep a `corp_action_suspect` flag when a split or adjustment looks inconsistent (missing split, adjustment that does not match the vendor’s own unadjusted series, or a gap that is not explained by a known action). Chat 3 must be able to refuse a suspect series.
4. Implement `EventProvider` with Finnhub only (`FINNHUB_API_KEY`): earnings calendar and dividend calendar. Map them so Chat 3 can apply earnings blackout T−2 through T+1 when `earnings.strict` is true (it defaults true), and ex-div warn versus block from `exdiv.strict` (default false) and `exdiv.block_yield_gte` (default 0.01).
5. Implement `CalendarProvider.next_open`. Use the NYSE calendar, including holidays and early closes. Return an ISO timestamp in `America/New_York`. Do not use “tomorrow weekday” as the calendar.
6. Tests use fixtures and recorded responses. Do not require network in `uv run pytest`. A missing `FINNHUB_API_KEY` or `MASSIVE_API_KEY` returns a typed data error and does not crash import or `swing analyze --help`.
7. Leave `ChecklistBrain` free of HTTP clients. Pass bars into the brain only through a data object Chat 3 can accept. Do not pass `ResearchResult` into indicator code.

## Env keys

| Key | Chat | Notes |
|---|---|---|
| `CONTEXT_DEV_API_KEY` | done (optional) | News enrichment only. Not bars |
| `CONTEXT_DEV_BASE_URL` | done (optional) | Default `https://api.context.dev/v1`. Non-https URLs (except localhost) are refused and do not send the key |
| `SWING_DATA_DIR` | done | Overrides the data root and, when `config.toml` sits in that directory, config discovery |
| `FINNHUB_API_KEY` | you | Events and calendars only |
| `MASSIVE_API_KEY` | you | Bars when provider is `massive`. Pay Massive Starter (~$29) only when Basic rate or history limits hurt. That is a billing choice, not a code default |
| `SWING_BARS_PROVIDER` | done | `yfinance` or `massive` |
| `SWING_CONFIG` | done | TOML path. Wins over `SWING_DATA_DIR/config.toml` |

No key is required to run the skeleton.

## Do not change

- Hash algorithm in `src/swing/hashing.py`
- Mutex order `BO_RVOL` > `PB_EMA` > `RSI2_MR`
- Default risk `0.01`, heat `0.06` / `0.03`, max positions `4`, RSI max `10`, SPY R² warn at `0.70` / 60 sessions
- `research.affects_checklist_math = false`
- `shariah.screen_in_v0 = false`
- Disclaimer text, except to extend it if a new claim needs a denial
- Time-stops. Research sketched 5 / 15 / 20 sessions and Ziad did not lock them. Leave them out of config

If you add a field to `SwingConfig`, the config hash changes for every user. Do that only for real policy, and say so in your handover.

## Known risks

- Verified on Linux in the agent VM. macOS paths are covered by unit tests (`tests/test_paths.py`), not by a run on a Mac.
- yfinance is an unofficial prototype and can break without notice. Massive is the intended bars vendor when limits hurt.
- Finnhub candle endpoints are the easy mistake. They are out of policy.
- Context search costs credits and can take the full 8 second timeout. Failure is `WARN_RESEARCH_ERROR`, not a crash. Headlines are not deterministic, so they stay off the checklist.
- `account.equity_usd` is null until Ziad sets it. Sizing cannot be correct without it. Do not invent an equity number.
- A high SPY R² is a warning, never a hard block.
- Inverse-ETF short proxies are not detected. Do not add a block list that pretends to be a Shariah ruling.
- `IbkrBrokerStub` must keep raising. No live orders.
- The envelope can represent `ENTER_LONG` only with `confidence: "checklist_only"`, `side: "long"`, and a plan. The skeleton never emits that decision. Do not emit it from the data layer.
