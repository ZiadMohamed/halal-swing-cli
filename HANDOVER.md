# Handover — Chat 3 (Brain)

Chat 2 shipped the data layer. Your job is the checklist brain: gates, indicators, the setup mutex, size, and heat. Do not place orders, do not write the paper journal, and do not restyle the terminal. Those are Chats 5 and 4.

Read [docs/architecture.md](docs/architecture.md) before editing. The product locks are already in `SwingConfig`. Do not invent a fatwa, a Shariah screen, or a trading edge.

## What Chat 2 shipped

- `yfinance` (default bars), `pyarrow` (Parquet), and `exchange-calendars` (NYSE). No extra HTTP library. Massive and Finnhub use the stdlib client. `uv.lock` is universal, including macOS arm64 and x86_64 wheels.
- `BarProvider.fetch_daily(ticker, lookback_sessions)`:
  - `yfinance` when `data.bars_provider` is `yfinance` (the default). `auto_adjust=True`, so OHLC is split- and dividend-adjusted.
  - Massive Basic when it is `massive` and `MASSIVE_API_KEY` is set. `adjusted=true` is split-adjusted only (Massive's own meaning). Unadjusted bars are fetched beside them for the suspect check.
  - Finnhub is rejected as a bars provider. There is no candle call.
- Parquet cache at `bars_cache_dir()` (`~/Library/Application Support/swing/cache/bars/{TICKER}.parquet` on macOS). A fresh file is reused when its last session is the last completed NYSE session and it holds at least `lookback` rows. Early closes count as completed after that day's close (13:00), not as holidays.
- `FinnhubEvents`: earnings calendar and cash dividend calendar only.
- `NyseCalendar.next_open(after_iso)` returns the next regular open strictly after that timestamp, as an ISO string in `America/New_York` (`09:30:00` with `-05:00` or `-04:00`). Holidays are skipped. The Friday after Thanksgiving is a session.
- `swing analyze` loads that bundle and copies a summary onto `envelope.data`. The decision is still `NO_TRADE` / `PIPELINE_NOT_IMPLEMENTED`. `stage` is still `"skeleton"`. No RSI, ATR, or size is computed.
- `StubBrain.evaluate(ticker, config, market=None)` accepts `MarketData` and ignores it. A brain that does not take `market` still runs. Research is never an argument.

`uv run pytest` does not use the network (82 tests after Chat 1's 35, plus the data suite). `uv run swing analyze --help` does not need vendor keys.

## How you consume data

Call `load_market_data(ticker, config)` or read the `market` argument. Do not construct HTTP clients in the brain. Do not pass `ResearchResult` into indicator code.

```python
from swing.data import load_market_data
from swing.data.models import DEFAULT_LOOKBACK_SESSIONS, MarketData

market = load_market_data("AAPL", config)  # lookback defaults to 320 sessions
series = market.bars                       # None when the bars vendor failed
```

`BarSeries.bars` is oldest-first. Each `DailyBar` has `session`, split-adjusted `open` / `high` / `low` / `close`, `volume`, and `raw_close` (unadjusted close, for audit only). Use `close` for indicators.

| Field | Use |
|---|---|
| `market.bars.corp_action_suspect` | If true, do not run indicators. `NO_TRADE`. |
| `market.bars.corp_action_reasons` | `missing_split`, `adjustment_mismatch`, `unexplained_gap` |
| `market.bars.adjustment` | `split_and_dividend` (yfinance) or `split` (Massive) |
| `market.earnings` | `report_date` is T. `hour` is `bmo`, `amc`, `dmh`, or `unknown` |
| `market.dividends` | `ex_date`, `amount` (cash per share), `currency` |
| `market.next_open` | ISO timestamp already in `America/New_York` |
| `market.events_known` | False when Finnhub failed or the key was missing |
| `market.errors` | `missing_api_key:MASSIVE_API_KEY`, `missing_api_key:FINNHUB_API_KEY`, or `vendor_error:...` |
| `market.status` | `ok`, `partial` (bars ok, events not), or `error` (no bars) |

`analyze` already passes this object when `evaluate` has a `market` parameter. Keep research off that signature.

SPY for the R² warning is not attached. Fetch it with the same bar provider: `fetch_daily("SPY", config.spy_r2.lookback_days)` or `load_market_data` is ticker-scoped, so call the provider directly. A high SPY R² stays `WARN_SPY_R2` only.

The envelope `data` object is a summary (counts, suspect flag, earnings dates, dividend amounts, `next_open`, errors). The full series is `MarketData.bars`, and the same rows are in the Parquet file. Do not recompute the suspect flag unless you are looking at `raw_close` yourself.

`DEFAULT_LOOKBACK_SESSIONS` is 320. That is not a hashed config field. SMA(200) needs the tail of this window.

### corp_action_suspect

True when the adjusted series and the vendor's unadjusted series disagree, or a large gap has no listed action. Chat 3 must refuse the series.

- `missing_split` — unadjusted close jumps by a common split ratio (2, 3, 4, 5, 10, 3-for-2, and the inverses, within 3%) and the vendor listed no split on that session. A real crash of that size is flagged too. That is intentional.
- `adjustment_mismatch` — a listed split is still visible in the adjusted series, split-adjusted closes do not rebuild from unadjusted closes and the listed splits (Massive, 2% tolerance), or a dividend-adjusted series (yfinance) still contains the dividend drop.
- `unexplained_gap` — adjusted close-to-close move of 40% or more, and no listed split or cash dividend accounts for it. A 39% move is not this flag.

Massive dividends used for this check come from `/stocks/v1/dividends`. They are not the ex-div calendar. The ex-div calendar is Finnhub only.

### Earnings and ex-div

This layer does not decide blackout or warn-versus-block.

- Earnings: T is `EarningsEvent.report_date`. When `earnings.strict` is true (the default), black out NYSE sessions from T minus `blackout_before_days` (2) through T plus `blackout_after_days` (1). Use `NyseCalendar`, not calendar-day arithmetic. `hour` tells you whether the print is before the open (`bmo`) or after the close (`amc`).
- Ex-div: yield is `amount / prior adjusted close`. `exdiv.strict` false (default) means an ordinary ex-div warns (`WARN_EXDIV`). Yield at or above `exdiv.block_yield_gte` (0.01) still blocks. `strict = true` blocks the ex-div window.
- `events_known` is false when the Finnhub call did not succeed. An empty `earnings` or `dividends` tuple in that case means unknown, not "no event". Do not treat it as a clear calendar. Strict earnings with an unknown calendar should not become `ENTER_LONG`.

Finnhub window requested: 30 calendar days back through 180 calendar days forward, America/New_York. The free earnings calendar may return a shorter slice. We do not invent dates to fill it.

`/stock/dividend` is the cash-dividend endpoint (ex-date in `date`, cash per share in `amount`). Finnhub marks that route premium. A free key can come back as `vendor_error:finnhub:...` with `events_known` false. Do not synthesize dividends.

### Calendar

`market.next_open` is the next open after "now". For another timestamp, `NyseCalendar().next_open(after_iso)`. Naive timestamps are read as New York. Exactly 09:30 returns the following session. July 3 2026 (observed Independence Day) is closed. November 28 2025 opens at 09:30 and closes at 13:00.

### Keys

| Key | Role |
|---|---|
| `CONTEXT_DEV_API_KEY` | Optional news. Not bars. Not checklist math |
| `CONTEXT_DEV_BASE_URL` | Default `https://api.context.dev/v1` |
| `SWING_DATA_DIR` | Data root. Also `config.toml` discovery |
| `FINNHUB_API_KEY` | Earnings and dividends only. Never bars |
| `MASSIVE_API_KEY` | Bars only when `bars_provider` is `massive`. Header `Authorization: Bearer`. Not placed in the URL |
| `SWING_BARS_PROVIDER` | `yfinance` or `massive` |
| `SWING_CONFIG` | TOML path |

Missing `MASSIVE_API_KEY` or `FINNHUB_API_KEY` raises `MissingApiKeyError` from the provider and is stored on the bundle. Import and `swing analyze --help` do not need the keys. `swing analyze TICKER` still prints an envelope and exits 0.

Massive routes: `GET /v2/aggs/ticker/{ticker}/range/1/day/{from}/{to}`, `GET /stocks/v1/splits`, `GET /stocks/v1/dividends`, host `https://api.massive.com`.

## What is still stubbed

| Piece | Where | Behavior now |
|---|---|---|
| Checklist | `StubBrain` | `NO_TRADE`, every gate `not_run`. Replace this |
| Text/JSON polish, Cairo clock | `output/render.py` | Disclaimer, hash, gates, a one-line data summary. Chat 4 |
| Paper JSONL | `journal/paper.py` | Raises. Chat 5 |
| IBKR | `broker/ibkr.py` | Raises. Stays unwired |

`analyze` copies `ChecklistResult.confidence`, `side`, and `plan` onto the envelope. Set those on the result when you emit `ENTER_LONG` (`confidence="checklist_only"`, `side="long"`, and a plan). Do not hardcode them in the orchestrator. There is no `ENTER_SHORT`.

Widen `Envelope.stage` when you leave the stub. Do not flip it to look finished while gates are still `not_run`.

`account.equity_usd` is null until Ziad sets it. Sizing cannot be correct without it. Do not invent an equity number.

## Do not change

- Hash algorithm in `src/swing/hashing.py`. Chat 2 added no `SwingConfig` field, so the hash is unchanged
- Mutex order `BO_RVOL` > `PB_EMA` > `RSI2_MR`
- Default risk `0.01`, heat `0.06` / `0.03`, max positions `4`, RSI max `10`, SPY R² warn at `0.70` / 60 sessions
- `research.affects_checklist_math = false`
- `shariah.screen_in_v0 = false`
- Disclaimer text, except to extend it if a new claim needs a denial
- Time-stops. They are not in config
- `IbkrBrokerStub` must keep raising

## Known risks

- Verified on Linux. macOS paths are unit-tested, not run on a Mac. `uv.lock` pins macOS wheels for pyarrow, numpy, and the rest.
- yfinance is an unofficial prototype. Massive is the bars vendor when Basic limits hurt (about two years of daily aggregates on the basic plan). Paying for Starter is a billing choice, not a code default.
- Finnhub candle endpoints are out of policy. The events module does not call them.
- Context search stays fail-soft and off the checklist. `WARN_NEWS` is still reserved for a soft note after numbers are fixed.
- A suspect series includes some real 50% crashes. Refusing them is the safe default.
- Inverse-ETF short proxies are not detected. Do not add a block list that pretends to be a Shariah ruling.
