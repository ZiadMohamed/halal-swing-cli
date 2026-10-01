# Handover — Chat 4 (Output)

Chat 3 shipped the checklist brain. Your job is the terminal: text and JSON polish, and the Cairo clock next to the New York fill time. Do not change indicator math, do not place orders, and do not write the paper journal. Those stay as they are; the journal is Chat 5.

Read [docs/architecture.md](docs/architecture.md) before editing. The product locks are already in `SwingConfig`. Do not invent a fatwa, a Shariah screen, or a trading edge.

## What Chat 3 shipped

`ChecklistBrain.evaluate(ticker, config, market=None, spy_bars=None, positions=(), sector=None)` walks `PIPELINE_GATES` in order. `analyze` uses it by default. `StubBrain` is still importable and still returns `NO_TRADE` / `PIPELINE_NOT_IMPLEMENTED` with every gate `not_run`. Research is never an argument.

`uv run pytest` does not use the network. `uv run swing analyze --help` does not need vendor keys.

### Decision

| Outcome | When |
|---|---|
| `ENTER_LONG` | Every gate is `pass` or `warn`, and a plan exists |
| `NO_TRADE` | A checklist gate stopped the walk |
| `BLOCK` | Product guard only (`BLOCK_SHORT`, `BLOCK_MARGIN`, `BLOCK_DERIVATIVE`). The brain does not emit `BLOCK` |

`ENTER_LONG` always has `confidence="checklist_only"`, `side="long"`, and a plan. There is no `ENTER_SHORT`. Confidence is absent otherwise. Shariah codes are not emitted. Zoya is not called.

`plan.setup` is `BO_RVOL`, `PB_EMA`, or `RSI2_MR`. `plan.entry` is the signal close (the last split-adjusted close). `plan.stop` is `entry - 1.5 * ATR(14)`. `plan.target` is `entry + 2 * (entry - stop)`. `plan.size_shares` is `floor(equity_usd * 0.01 / (entry - stop))`. `plan.next_open` is copied from `market.next_open`. That timestamp is the fill. The opening print is not known yet, so stop and target are measured from the signal close.

### Stage

`Envelope.stage` is `skeleton`, `partial`, or `checklist`.

- `skeleton` — every gate is `not_run`. Product blocks stay here. So does an explicit `StubBrain`.
- `partial` — the brain ran and at least one later gate is still `not_run`.
- `checklist` — every gate is `pass`, `warn`, `block`, or `no_trade`. An `ENTER_LONG` is `checklist`. A finished `NO_TRADE` (the failing gate is the last one that had to run) is also `checklist`.

Do not treat `partial` as a finished checklist. Do not paint every gate green.

### Gates

Order is unchanged: `data_auth`, `liquidity`, `soft_veto`, `earnings`, `regime`, `heat`, `adr`, `setup_mutex`, `rr_stop`, `next_open`.

A hard stop leaves later gates at `not_run`. Status `warn` does not change entry, stop, target, size, or `next_open`. Status `block` on `soft_veto` is still decision `NO_TRADE` (ex-div). It is not a product `BLOCK`.

| Code | Role |
|---|---|
| `NO_MARKET_DATA` | No bars, or the signal close is not a positive finite price |
| `CORP_ACTION_SUSPECT` | Indicators are not run. Reasons from the data layer are in the message |
| `ILLIQUID` | Fewer than 20 sessions, or the 20-session average of `close * volume` is not positive. No dollar floor was locked |
| `WARN_EXDIV` | Entry session is the ex-date and the cash yield is below `exdiv.block_yield_gte`. `exdiv.strict` is false |
| `EXDIV_BLOCK` | Same session, and either `exdiv.strict` or yield `>= block_yield_gte` (default 0.01). Yield is `amount / prior adjusted close` |
| `EARNINGS_UNKNOWN` | `earnings.strict` and `events_known` is false. An empty earnings tuple is not a clear calendar |
| `EARNINGS_BLACKOUT` | Strict blackout. NYSE sessions from T−`blackout_before_days` through T+`blackout_after_days`. The entry session has to fall inside. `hour` (`bmo`, `amc`, `dmh`, `unknown`) is named and does not move the window |
| `WARN_SPY_R2` | R² of daily returns versus SPY over `spy_r2.lookback_days` (60) is `>= 0.70`. Warning only |
| `HEAT_LIMIT` | Open risk plus 1% would exceed total heat 6% or, when `sector` is set, sector heat 3% |
| `MAX_POSITIONS` | Open count is already 4 |
| `ADR_TOO_QUIET` | 20-session mean of `(high-low)/close` is not positive |
| `NO_SETUP` | None of the three setups matched |
| `SETUP_SUPPRESSED` | A lower setup also matched. Warning. Mutex keeps the winner |
| `EQUITY_UNSET` | `account.equity_usd` is null. No size is invented |
| `SIZE_BELOW_ONE_SHARE` | 1% of equity does not buy one share. Equity `0` lands here. Null does not |
| `INVALID_STOP` | ATR is not positive or the stop is not strictly below the entry |
| `NO_NEXT_OPEN` | `market.next_open` is missing or not a timestamp |

Setups, evaluated only after the earlier gates pass:

- `BO_RVOL`: close above SMA(50), close above the prior 20-session high, volume at least 1.5 times the prior 20-session volume average (today excluded).
- `PB_EMA`: close above EMA(50), low at or through EMA(20), close back above EMA(20).
- `RSI2_MR`: close above SMA(200), Wilder RSI(2) strictly below 10.

Indicators use `close`, `high`, `low`, and `volume`. They do not read `raw_close`.

### SPY and the open book

`analyze(..., fetch_market=True)` loads the ticker, then loads `SPY` with the same `load_market_data` path and `lookback_sessions=config.spy_r2.lookback_days`, unless the ticker series is missing or `corp_action_suspect`. A suspect or missing SPY series does not block and does not warn. Pass `spy_bars` to skip that fetch. The brain does not construct an HTTP client.

The CLI calls the brain with `positions=()` and `sector=None`. The paper journal is still unwired, so the command Ziad runs does **not** know open risk. Heat and the 4-position cap are enforced only when the caller passes them:

```python
analyze(ticker, positions=(OpenPosition(ticker="MSFT", risk_fraction=0.02, sector="tech"),), sector="tech")
```

`risk_fraction` is the fraction of equity at risk, not a share count. Sector heat runs only when `sector` is a non-empty string. Missing sectors are not lumped into one bucket. Chat 5 should pass the book. Do not read `journal.jsonl` from the renderer.

### What the text view still gets wrong

`output/render.py` still appends `stage: … — brain not run` whenever the view is not compact. That sentence is stale. JSON is the accurate envelope. Compact text already hides the gate list and still prints the disclaimer.

Show, on every non-compact view and in a shorter form when `--compact` is set:

- decision, reason codes, warning codes
- plan when present: setup, entry, stop, target, size, `next_open`
- `next_open` in `America/New_York`, and the same instant in `Africa/Cairo` (`timezone.user`)
- gate name and status
- the disclaimer, including compact

`--compact` stays default off. `--json` stays a single JSON document on stdout. Do not drop `config_hash`, `shariah.screened=false`, or `research.affects_checklist_math=false`.

`WARN_NEWS` is still unused. Do not let a headline change numbers.

## Do not change

- Hash algorithm in `src/swing/hashing.py`. Chat 3 added no `SwingConfig` field. The hash encoding is unchanged. `plan.setup` is envelope output, not hashed policy
- Mutex order, risk `0.01`, heat `0.06` / `0.03`, max positions `4`, RSI max `10`, SPY R² warn at `0.70` / 60 sessions
- `research.affects_checklist_math = false`
- `shariah.screen_in_v0 = false`
- Disclaimer text, except to extend it if a new claim needs a denial
- Time-stops. They are not in config
- `IbkrBrokerStub` must keep raising
- `PaperJournal` must keep raising
- Indicator formulas and gate order

## Known limits

- Verified on Linux. macOS paths are unit-tested, not run on a Mac.
- The CLI open book is empty until Chat 5. A fourth open position elsewhere is invisible to `swing analyze` today.
- The ticker's sector is not on `MarketData`. Sector heat needs the `sector` argument.
- Liquidity is "20 sessions and positive average dollar volume". Prefs 1–12 did not lock a $20M floor, so none was added.
- ADR is that 20-session range. It is not a second copy of ATR. ATR is only the stop.
- A suspect series still includes some real crashes. Refusing them is the safe default.
- Inverse-ETF short proxies are not detected. High R² warns in either direction. Do not add a block list that pretends to be a Shariah ruling.
