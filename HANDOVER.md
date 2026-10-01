# Handover — Chat 5 (Hardening)

Chat 4 shipped the terminal. Your job is hardening: synthetic fixtures, acceptance tests, and the append-only paper journal. Do not place orders. `IbkrBrokerStub` stays unwired and keeps raising. Do not change indicator math, and do not restyle the clocks unless a test shows they are wrong.

Read [docs/architecture.md](docs/architecture.md) before editing. The product locks are already in `SwingConfig`. Do not invent a fatwa, a Shariah screen, or a trading edge.

## What Chat 4 shipped

`output/render.py` prints the envelope. `uv run pytest` does not use the network. `uv run swing analyze --help` does not need vendor keys.

### Text

`render_text(envelope, *, user_tz="Africa/Cairo", market_tz="America/New_York")`. The CLI passes `config.timezone.user` and `config.timezone.market`. Defaults match the locked clocks. `--compact` is still default off (`output.compact` in TOML can turn it on without the flag).

Both views show:

- `TICKER  DECISION`
- `config_hash`
- reason codes and warning codes, when any exist (codes only, not the message text)
- the plan, when present: `setup`, `entry`, `stop`, `target`, `size`, `next_open`
- gate name and status
- the disclaimer, last, including compact

Full view, one gate per line: `  data_auth: pass`. Compact is one line: `gates: data_auth=pass liquidity=not_run ...`. Compact clocks are one line, joined with ` | `. Research status is still printed when it is not `ok` (`research: skipped (missing_api_key)`). The data summary (`bars=`, `clean` or `suspect`) is still printed when data was loaded. Hit titles and snippets are not printed. They stay on the JSON envelope.

`stage` wording:

| Stage | Line |
|---|---|
| `skeleton` and `data.status == not_loaded` | `stage: skeleton — data and brain not run` |
| `skeleton` otherwise (`StubBrain`, bars already loaded) | `stage: skeleton — brain not run` |
| `partial` or `checklist` | `stage: partial` or `stage: checklist` |

`partial` and `checklist` mean `ChecklistBrain` ran. Those lines do not say the brain was skipped. A product `BLOCK` is still `skeleton` with data not loaded, so the "not run" sentence stays true there.

### Clocks

`next_open` is one instant shown twice.

- Market clock: `America/New_York` unless `timezone.market` is overridden. October open: `2026-10-05T09:30:00-04:00`. January open: `2026-01-02T09:30:00-05:00`.
- User clock: `timezone.user`, default `Africa/Cairo`. The same October instant is `2026-10-05T16:30:00+03:00`. The January instant is `2026-01-02T16:30:00+02:00` (Cairo standard time). Do not hardcode `+03:00` for every month.
- The fill stamp is `plan.next_open` when a plan exists. Otherwise `data.next_open`. If those two strings differ, both instants are printed.
- A naive timestamp is read as the market zone, same rule as `NyseCalendar`.
- A stamp that does not parse is printed raw (`next_open not-a-timestamp`). No offset is invented.

JSON does not grow a second clock field. The ISO string already identifies the instant. `--json` is `Envelope.model_dump(mode="json")`, indented, one document, trailing newline, nothing else on stdout.

### What the renderer does not do

`WARN_NEWS` is still unused by the brain. If a warning with that code is already on the envelope, the text prints the code and does not copy the headline into the plan line. Entry, stop, target, size, and `next_open` in the text match the envelope. `research.affects_checklist_math` stays `false`. `shariah.screened` stays `false`. `config_hash` is unchanged. The disclaimer text is unchanged.

The renderer does not read `journal.jsonl`, does not size a trade, and does not call the broker.

## What is still stubbed

| Piece | Where | Behavior now |
|---|---|---|
| Paper JSONL | `journal/paper.py` | `PaperJournal.append` raises `NotImplementedError`. `tests/test_product_locks.py` expects that raise |
| Open book on the CLI | `cli.py` → `analyze` | `positions=()` and `sector=None`. Heat and the 4-position cap do not see a previous plan |
| IBKR | `broker/ibkr.py` | `place_order` raises. Leave it |

`journal_path()` is the file. macOS: `~/Library/Application Support/swing/journal.jsonl`. `SWING_DATA_DIR` overrides the root. On Linux the root is `$XDG_DATA_HOME/swing` or `~/.local/share/swing`. The path helper does not create the file.

`OpenPosition` is what the heat gate already accepts:

```python
analyze(
    ticker,
    positions=(OpenPosition(ticker="MSFT", risk_fraction=0.02, sector="tech"),),
    sector="tech",
)
```

`risk_fraction` is the fraction of equity at risk, not a share count. Sector heat runs only when `sector` is a non-empty string. Missing sectors are not lumped into one bucket. The ticker's sector is not on `MarketData`. v0 has no sector vendor.

A planned long does not store `risk_fraction` on the envelope. The shares and prices are on `plan`: `size_shares * (entry - stop) / equity_usd` is the fraction actually at risk, and it is at most `risk.per_trade` because size is floored. Record that fraction. Do not recompute the share count in the journal.

## What to build

- Append-only paper JSONL at `journal_path()`. One JSON object per line. Append a line when the decision is `ENTER_LONG` (a planned entry). Do not rewrite or delete earlier lines. `NO_TRADE` and `BLOCK` are not plans. A second `analyze` that again returns `ENTER_LONG` appends a second line.
- Call the journal from the orchestrator or the CLI, after the envelope exists. Do not write it from `output/render.py`.
- Load open risk from that file and pass `positions` into `analyze` so the command Ziad runs enforces heat `0.06`, sector heat `0.03`, and `max_concurrent_positions` `4`. Today those gates only see the arguments a caller passes.
- Synthetic fixtures and acceptance tests for `ENTER_LONG`, `NO_TRADE`, `BLOCK`, and a warn path (`WARN_EXDIV`, `WARN_SPY_R2`). Include the text clocks (New York and Cairo, summer and winter offsets). No network. `uv run pytest` stays offline.
- Update `tests/test_product_locks.py` when `PaperJournal.append` stops raising. Keep the `IbkrBrokerStub` assertion. That test still requires the IBKR error text to mention that live trading is out of scope.

`account.equity_usd` is still null until Ziad sets it. Do not invent an equity number. Without it the brain returns `EQUITY_UNSET` and there is no plan to journal.

## Do not change

- Hash algorithm in `src/swing/hashing.py`. No new `SwingConfig` field unless you are adding journal policy on purpose. A new hashed field changes `config_hash`
- Mutex order, risk `0.01`, heat `0.06` / `0.03`, max positions `4`, RSI max `10`, SPY R² warn at `0.70` / 60 sessions
- `research.affects_checklist_math = false`
- `shariah.screen_in_v0 = false`
- Disclaimer text, except to extend it if a new claim needs a denial
- Time-stops. They are not in config
- `IbkrBrokerStub.place_order` must keep raising
- Indicator formulas and gate order
- The text contract above: decision, codes, plan fields, both clocks, gate name and status, disclaimer on compact

## Known limits

- Verified on Linux. macOS paths are unit-tested, not run on a Mac.
- The CLI open book is empty until you pass it. A fourth open position elsewhere is invisible to `swing analyze` today.
- Liquidity is "20 sessions and positive average dollar volume". Prefs 1–12 did not lock a dollar floor.
- ADR is the 20-session mean of `(high-low)/close`. It is not a second copy of ATR. ATR is only the stop.
- A suspect series still includes some real crashes. Refusing them is the safe default.
- Inverse-ETF short proxies are not detected. High R² warns in either direction. Do not add a block list that pretends to be a Shariah ruling.
- `WARN_NEWS` is still not attached by the brain. Do not let a headline change entry, stop, target, size, or `next_open`.
