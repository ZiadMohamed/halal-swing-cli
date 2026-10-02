# halal-swing-cli — Redesign plan (design review + research)

Status: **proposal only. No product code, tests, TOML, or CI were changed to produce this document.**
Date: 2026-10-02. Reviewer: cloud agent (Linux VM). Product runtime: macOS.
Priority order, as set by Ziad on 2026-10-02: **profit and product first; ease of setup last.** Halal locks are not negotiable and are not traded for profit.

Not financial advice. Not a Shariah certification. Every performance number below comes from throwaway simulations on a survivorship-biased sample. They are directional evidence for design choices, not a forecast.

---

## 1. Executive summary

**What is broken today (verified, not guessed):**

1. **The Finnhub 403 is a code bug, not a key problem.** Every run calls Finnhub `/stock/dividend`, which Finnhub's own docs mark *Premium*. The free key authenticates (an invalid key returns **401** "Invalid API key"; a valid free key on a premium endpoint returns **403**). `data/factory.py` then sets `events_known=False` for *all* events when the dividend call fails. That throws away the earnings data the free endpoint returned, and strict earnings blocks every trade with `EARNINGS_UNKNOWN`.
2. **Yahoo bars break in exactly Ziad's decision window.** The latest completed session can come back with NaN open/high/low/close (and valid volume) until the next US open. That is a known Yahoo issue, observed live on 2026-10-01 for AAPL, MSFT, SPY, NVDA, KO. The parser turns NaN into `0.0`, the series becomes `CORP_ACTION_SUSPECT`, and the poisoned series is cached as fresh. Every ticker would return `NO_TRADE` that night even with earnings fixed. During US hours (Cairo evening) the signal is computed on a partial bar instead.
3. **The journal bricks the tool.** Every `ENTER_LONG` analyze appends a line, and nothing ever closes one. Four runs, even of the same ticker, produce `MAX_POSITIONS` forever.
4. **Sizing ignores cash.** At 1% risk with a 1.5×ATR stop, the median position is **32% of equity**, and 72% of trades exceed 25%. Four positions need about 128% of equity, which a cash account cannot fund. If the IBKR account is actually margin, the overflow would be borrowed (riba).

**What the evidence says about profit (Section 2 and Appendix A):**

- With the same stop and target, the three v0 entries (BO_RVOL, PB_EMA, RSI2_MR) did **not** beat random-day entries (+0.133R vs +0.164R per trade). The mutex is cosmetic: all three setups get identical stop, target and size.
- At portfolio level (cash-constrained, 2021–2026), **v0 returned 3.4% CAGR against 17.6% for SPUS buy-and-hold.** The levers that helped were:
  - cross-sectional **momentum ranking** of candidates (11.9% vs 3.0% with random ranking);
  - a **trailing stop** instead of the fixed 2R target (11.9% vs 7.7%);
  - **five slots at 20%** each instead of four (13.9%);
  - **exiting before earnings** (7.7% vs 5.8% for holding through the report).
  Doubling risk to 2% hurt. A tight "max-chase" entry limit hurt.
- **No swing variant beat holding SPUS over 2021–2026,** even with survivorship bias in the swing variants' favour. The product must measure itself against that benchmark, and Ziad must decide on a core-satellite split.

**What stays:** Python 3.12 + uv, cash-long-only USD, manual IBKR placement, user-supplied screened tickers, the NYSE calendar, ATR(14) stops, 1% risk, strict earnings for single stocks, `config_hash`, a JSON output.

**What changes:**

- **Product shape.** The product becomes a daily *universe* workflow (`scan` → ranked entries plus exits due → IBKR order tickets → record fills → review against SPUS) instead of one-ticker `analyze`.
- **Algorithm.** Keep the three detectors as triggers behind a 200-day trend filter. Add momentum ranking, a regime gate, a 1.5×ATR initial stop plus a 3×ATR fixed trailing stop, exit at the close before earnings, and five slots capped at 20% notional and by available cash.
- **Data.** Two free keys (Massive for official end-of-day bars, Finnhub for earnings), with yfinance as the fallback and earnings cross-check. Finnhub premium endpoints are never called. Context.dev is removed.
- **Measurement.** A portfolio backtest harness that runs the *same brain code*, plus random-rank and buy-and-hold baselines, plus automatic forward-scoring of every plan.
- **Deletions.** Research/Context.dev, IBKR stub, StubBrain, ports stubs, product-guard indirection, reserved Shariah codes, mutex, SPY R² warning, heat/sector caps, ADR gate, `--compact`, the corp-action heuristic module, prose-asserting tests.

**Why:** spend complexity only where it moves profit (ranking, exits, capacity, correct data, measurement) or protects capital without costing profit (cash cap, earnings exit). Delete everything else.

---

## 2. Fresh research findings (with sources)

### 2.1 Repo facts (read and run on 2026-10-02)

- 3,759 lines of `src`, 3,954 lines of tests, 184 tests passing (`uv run pytest`, offline). About 118 assertions check prose substrings.
- Pipeline: `cli.main` → `load_project_env` (CWD `.env`, then data-dir `.env`) → `load_config` → `PaperJournal.load_positions` → `analyze` → `load_market_data` (bars + Finnhub earnings + Finnhub dividends + NYSE next open) → a second `load_market_data("SPY")` for R² → `ChecklistBrain` → Context.dev search → envelope → journal append.
- `FinnhubEvents.dividend_calendar` calls `/stock/dividend`. In `factory.load_market_data`, a dividend failure sets `events_failed=True`, so `events_known=False`, so `EARNINGS_UNKNOWN`. Earnings and dividend failures produce the *same* error string (`vendor_error:finnhub:http_403:Forbidden`), and `http.get_json` discards the response body.
- `yfinance_bars._float` maps NaN to `0.0`. The provider downloads twice (adjusted and raw). The cache `read_fresh_bars` treats a series as fresh when its last session equals the last completed session, even if that bar is all zeros.
- `MassiveBarProvider.fetch_daily` makes at least 4 requests per ticker (adjusted aggs, raw aggs, splits, dividends). Ticker plus SPY is 8 requests, above Massive Basic's 5 calls per minute.
- Heat: `max_concurrent_positions=4` × `per_trade=0.01` means total heat is at most 4%, so the 6% cap can never bind. Sector heat applies only when `--sector` is passed.
- `ADR` and `liquidity` gates only check `> 0`. There is no dollar-volume floor.
- Product guards are called with constants (`side="long"`, `instrument="equity"`), so the only reachable block is `account.mode="margin"` from config.

### 2.2 Providers and earnings APIs

| Source | What we verified | Fit |
|---|---|---|
| **Finnhub free** | Docs navigation tags *Dividends* and *Dividends 2* as **Premium**; *Earnings Calendar* is free. Pricing page: free earnings calendar is "1 month and real-time updates (US)", 60 calls/min. Finnhub staff: a 403 means the endpoint is outside your plan. Live probe: an invalid key gets 401 `{"error":"Invalid API key"}` from both endpoints, including through the repo's own `get_json` client, which rules out a WAF or User-Agent block. | Earnings only, with a ≤35-day forward window. Never call `/stock/dividend`, `/stock/candle` or `/stock/split`. |
| **yfinance (Yahoo, no key)** | Live from a cloud IP: `Ticker.calendar` returned the next earnings date and ex-dividend date (AAPL 2026-10-29, MSFT 2026-10-28, NVDA 2026-11-17). `get_earnings_dates()` returned history back to 2020 with time of day. `history_metadata["instrumentType"]` returns `ETF`/`EQUITY` at no extra cost; the ETF calendar is empty. **Last daily bar NaN** is reproduced and known (#2895, #2925). `repair=True` needs scikit-learn (not installed), but rebuilding the bar from 1-hour bars works (open/high/low/close within ~0.05% of Yahoo's last price; summed hourly volume undercounts, so keep the daily volume). Rate limiting and TLS fingerprinting are recurring problems (`curl_cffi`, `YFRateLimitError`). | Earnings cross-check, instrument type, ex-div date. Fallback bars only. |
| **Massive (ex-Polygon) Basic, free key** | $0, 5 calls/min, end-of-day, 2 years of history. Daily aggregates, splits and dividends included. **Grouped daily** (`/v2/aggs/grouped/locale/us/market/stocks/{date}`) returns every US stock for a date in one call and is on Basic. Benzinga earnings is a paid add-on, not Basic. | **Primary bars.** One grouped call per day updates the whole universe; backfill once per ticker, throttled. |
| **Tiingo free** | 50 requests/hour, 1,000/day, 500 unique symbols/month. End-of-day prices are adjusted and include `divCash` and `splitFactor` in one response. | Documented alternative bars source if Massive limits hurt. |
| **Alpha Vantage free** | 25 requests/day. `EARNINGS_CALENDAR` (CSV, per symbol, horizon of 3, 6 or 12 months). The key goes in the query string as `apikey`, which `http.strip_secrets` deletes. | Optional third earnings source only. Too few calls for a universe. |
| **FMP free** | 250 calls/day; earnings calendar is paid-only (FMP FAQ). | Rejected. |
| **Nasdaq `api.nasdaq.com/api/calendar/earnings?date=`** | Works without a key from the VM, but only by date (one call per day of horizon). Unofficial. | Rejected for runtime; possible manual cross-check. |
| **Stooq CSV** | Now behind a JavaScript proof-of-work challenge. | Rejected. |
| **Survivorship-free research data** | Norgate Platinum (~$630/yr) is **Windows-only** (macOS needs a VM). Sharadar SEP on Nasdaq Data Link (REST, active and delisted since 1998) and EODHD (delisted list plus end-of-day) work from macOS. | Optional paid research data for the harness (open question). |

Sources:
- [Finnhub docs (navigation premium tags)](https://finnhub.io/docs/api/stock-dividends), [Finnhub pricing](https://finnhub.io/pricing), [Finnhub issue #534 (403 = outside plan)](https://github.com/finnhubio/Finnhub-API/issues/534), [#405](https://github.com/finnhubio/Finnhub-API/issues/405), [#459 (free earnings limited to 1 month)](https://github.com/finnhubio/Finnhub-API/issues/459)
- [yfinance #2895 (NaN last bar before open)](https://github.com/ranaroussi/yfinance/issues/2895), [#2925](https://github.com/ranaroussi/yfinance/issues/2925), [yfinance `_http.py` (curl_cffi)](https://github.com/ranaroussi/yfinance/blob/main/yfinance/_http.py), [rate-limit discussion #2431](https://github.com/ranaroussi/yfinance/discussions/2431)
- [Massive pricing](https://massive.com/pricing), [Massive grouped daily](https://massive.com/docs/rest/stocks/aggregates/daily-market-summary), [Massive dividends](https://massive.com/docs/rest/stocks/corporate-actions/dividends), [Massive Benzinga earnings (paid)](https://massive.com/docs/rest/partners/benzinga/earnings)
- [Tiingo pricing](https://www.tiingo.com/about/pricing), [Alpha Vantage key and limits](https://www.alphavantage.co/support/api-key/), [Alpha Vantage docs](https://www.alphavantage.co/documentation/), [FMP FAQ](https://site.financialmodelingprep.com/faqs)
- [Survivorship-free vendors compared](https://frontierledger.ai/strategy-backtesting-evaluation/survivorship-bias-free-equity-universes-data-vendors-compared), [Norgate (Windows-only)](https://stockmarketstack.com/tools/norgate-data), [EODHD delisted](https://eodhd.com/financial-apis/delisted-stock-companies-data-2)

### 2.3 Swing methods: what the literature supports

| Claim | Evidence | Implication |
|---|---|---|
| RSI(2) mean reversion still works | It has decayed. Connors RSI below 5 returned 1.5% over the next 5 days in 1990–2000 versus 0.3% in 2015–2025 (Zarattini). Single-day RSI(2)<5 on the S&P 1500 from 2015 to 2026 had a 63% win rate but a profit factor of 0.99 net of costs (quant4free). The edge exists in bull regimes, but almost all of it was before 2008 for SPY (Quantitativo). | Fine as a *trigger*; not an edge by itself. Needs a regime filter. |
| Short-term reversal | 30–50 bps/week net in large caps, negative in broad universes after costs (de Groot, Huij & Zhou 2012). Weaker in recent large-cap samples (Da, Liu & Schaumburg). | Restrict to liquid names; keep turnover moderate. |
| Momentum and 52-week-high proximity | Nearness to the 52-week high dominates past-return momentum, with no long-run reversal (George & Hwang 2004). Recency of the high matters (Bhootra & Hur 2013). | **Cross-sectional ranking by momentum is the best-supported long-only lever.** |
| Momentum crashes | Crashes happen in rebounds after bear markets, driven mostly by the short leg (Daniel & Moskowitz 2016). Long-only lags rather than crashes. | A regime filter is about drawdown control, not alpha. |
| Trend or regime filter | The 10-month (≈200-day) SMA rule cut S&P drawdown from 83.7% to 50.0% over 1900–2005 while raising CAGR (Faber 2007). | Use a regime gate as a drawdown tool; evidence on swing CAGR is mixed (Appendix A). |
| Post-earnings drift | Gone for large caps since about 2006 (Martineau 2022). | Do not build a drift setup. |
| Earnings gap risk | The average S&P 500 move on announcement day is about 2.5% each way, with fat tails. Implied moves are fairly priced, so there is no free lunch in holding through. | Holding through earnings breaks the 1% risk contract (worst trade in the smoke test: −6.5R). |
| IBKR order mechanics | A plain STP becomes a market order, so it can fill far through the stop on a gap. Plain stops don't work outside regular hours; stop-limit may not fill. Bracket children activate on the parent fill as one-cancels-other (OCA). | Size so a gap is survivable (notional cap); use STP plus TRAIL in an OCA group. |
| Cash accounts | US equities settle T+1 (since 2024-05-28). IBKR cash accounts need settled funds; good-faith and free-riding rules apply. | Never plan more than settled cash. |

Sources:
- [quant4free RSI(2)](https://quant4free.com/analysis/rsi2-mean-reversion/), [Quantitativo "Holy Grail"](https://www.quantitativo.com/p/the-holy-grail-still-works), [Zarattini CRSI out-of-sample](https://www.linkedin.com/pulse/how-connorrsi-performing-out-of-sample-carlo-zarattini-gysve)
- [de Groot, Huij & Zhou 2012](https://repub.eur.nl/pub/25718), [Da, Liu & Schaumburg](https://academicweb.nd.edu/~zda/Reversal.pdf)
- [George & Hwang 2004](https://www.bauer.uh.edu/tgeorge/papers/gh4-paper.pdf), [Bhootra & Hur 2013](https://ideas.repec.org/a/eee/jbfina/v37y2013i10p3773-3782.html), [Daniel & Moskowitz 2016](https://www.kentdaniel.net/papers/published/jfe_16.pdf)
- [Faber 2007](https://www.cambriainvestments.com/wp-content/uploads/2018/01/A-Quantitative-Approach-to-Tactical-Asset-Allocation.pdf), [Martineau 2022](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3111607), [Earnings Announcements: Ex-ante Risk (AEA 2024)](https://www.aeaweb.org/conference/2024/program/paper/5GGEki7i)
- [IBKR stop order](https://www.interactivebrokers.com/campus/glossary-terms/stop-order/), [IBKR bracket orders](https://www.interactivebrokers.com/campus/trading-lessons/bracket-orders-for-tws-mosaic-2/), [IBKR outside regular hours](https://www.interactivebrokers.com/campus/trading-lessons/trading-outside-regular-trading-hours-rth/)
- [IBKR T+1](https://www.interactivebrokers.com/campus/traders-insight/securities/stocks/t1-settlement-what-it-means-for-traders-and-investors/), [Fidelity cash-account violations](https://www.fidelity.com/learning-center/trading-investing/trading/avoiding-cash-trading-violations)

### 2.4 Smoke simulations run for this review

Throwaway scripts in `/tmp` on the VM, not committed: 50 current US large caps plus SPY/SPUS, yfinance adjusted daily bars 2013–2026, earnings dates from yfinance (2020 onward), fills at next open, 5 bps per side, $1 per order. The full method and tables are in **Appendix A**. Headline numbers are quoted in Sections 1, 4 and 9.

---

## 3. Challenges to the current design (claim → critique → recommendation)

1. **"Four isolated areas (data, brain, output, hardening) with ports, stubs and adapters."** This produced 3,759 lines for one decision, much of it dead: `StubBrain`, `Unimplemented*` ports, a raising `IbkrBrokerStub`, an `inspect.signature` brain adapter, and `guards.product_block` with constant arguments. → **Delete the dead layers.** Target modules: `data/`, `brain/`, `book`, `report`, `cli`. Safety comes from code that cannot place orders, not from a stub that raises.
2. **"`swing analyze TICKER` is the product."** Profit levers need a universe: cross-sectional ranking, slot allocation, and choosing the best 1–2 candidates per day. A single-ticker command cannot rank. → **`swing scan` (the whole universe) becomes the core command.** `analyze` stays as a detail view of one ticker.
3. **"Paper JSONL of planned `ENTER_LONG` lines is the open book."** Plans are not fills. Every analyze appends, re-running a ticker double-counts, nothing closes, and four plans brick the tool. → **Separate the two:** `book.jsonl` holds real buy/sell fills (append-only; open positions = buys minus sells), and `plans.jsonl` auto-logs every `ENTER_LONG` plan, deduplicated on (ticker, signal session, config_hash). Plans are forward-scored automatically and never count as risk.
4. **"Heat ≤6% total, ≤3% per sector, 4 positions."** The 6% cap cannot bind (4 × 1% = 4%). The sector cap needs a manual flag nobody passes. The binding constraint, cash, is ignored. → **Replace with slots × notional cap × available cash** (five slots, 20% each). Drop sector heat in v1.
5. **"Context.dev live research enriches the envelope."** By design it affects nothing (`affects_checklist_math=false`), yet it costs credits, an 8 s timeout and a key on every run. → **Delete.**
6. **"Four output modes (text, compact, simple, json)."** → **Three:** default action card, `--explain` (gates and numbers), `--json`.
7. **"Reserved Shariah codes, a `BLOCK` decision, and a margin guard."** None are emitted in v0, the guard can only trip on config, and the codes are unused. → Decisions are `ENTER_LONG` and `NO_TRADE`. `account.mode` becomes `Literal["cash"]` so config rejects margin at load. Delete the reserved codes until a screener exists. Keep the lock tests: no short path, no `ENTER_SHORT`, no broker dependency (for example, no `ib_insync`/`ib_async` in the lockfile).
8. **"The corp-action heuristic module (179 lines) plus double download."** It doubles Yahoo calls, misfires on NaN bars (observed live), and gives little protection that a split list doesn't. → **Replace with `sanitize()`:** drop non-finite or non-positive OHLC (never coerce to 0), enforce the freshness contract, flag a ≥40% unexplained one-day move. Use the vendor's split list. One download per ticker.
9. **"The signal uses whatever the last bar is."** That can be a partial bar during US hours or a NaN bar before the open. → **Freshness contract:** the signal bar must equal `last_completed_session(now)`; drop bars after it; never cache a non-final bar. Otherwise fall back to the next source, then `NO_TRADE DATA_STALE`.
10. **"`confidence: checklist_only` is the honesty mechanism."** It is a label with no measurement behind it. → **Add measurement:** a backtest harness on the same brain functions, random-rank and buy-and-hold baselines, forward plan scoring, and closed-trade review against SPUS.
11. **"Tests lock the prose."** About 118 prose assertions make every wording change a test edit. → Test behaviour and numbers; keep a few golden JSON fixtures.
12. **"`config_hash` on every envelope."** Cheap and useful. → **Keep,** and stamp it on plans and book entries.
13. **"Envelope schema 1.1.0, additive only."** It is a personal tool with no consumers. → Bump to **2.0.0** and drop research and stage cruft.

---

## 4. Challenges to the algorithm (claim → critique → recommendation)

| # | v0 claim / locked pref | Critique (evidence) | Recommendation |
|---|---|---|---|
| A1 | BO_RVOL, PB_EMA, RSI2_MR are the entries | Same stop and 2R target: v0 entries +0.133R ± 0.018 vs random day +0.164R ± 0.016 and random above SMA200 +0.142R. The entries carry no measurable edge. Literature: RSI(2) has decayed. | Keep all three as **triggers** (cheap, recognisable) behind a **trend filter** (close above SMA200, added to BO and PB). The edge has to come from ranking and exits. |
| A2 | Mutex BO > PB > RSI2 | Cosmetic: all setups get identical stop, target and size, so the winner only changes a label. | **Delete the mutex.** Record every matched trigger as a label. |
| A3 | RSI(2) < 10 | A fine trigger. RSI(2)-only fell to 4.5% CAGR vs 11.9% with all triggers (2021–26 portfolio test). | Keep the threshold at 10; don't make it the sole trigger. |
| A4 | (absent) Candidate ranking | Momentum ranking is the largest lever: 11.9% vs 3.0% CAGR with random ranking (2021+), and 13.5% vs 8.5% (2014+). Supported by George & Hwang and Jegadeesh & Titman. The smoke test inflates it most, because the survivor universe embeds future winners. | **Rank candidates by 6-month momentum** (close 5 sessions ago ÷ close 126 sessions ago − 1) across the universe, and fill slots from the top. Validate on survivorship-free data before trusting the size of the effect. |
| A5 | Exit = stop or 2R target | The fixed 2R target caps winners. A fixed 3×ATR trailing stop gave 11.9% vs 7.7% (2021+) and 13.5% vs 12.0% (2014+), at a lower win rate (~35–39%) and a deeper 2014+ drawdown. | **Default exit:** initial STP at entry − 1.5×ATR, plus a TRAIL order with a fixed amount of 3×ATR(14 at signal), in one OCA group. No fixed target. This is a human call (Q2). |
| A6 | Stop = entry − 1.5×ATR(14) | Reasonable initial stop. Gaps through the stop hit 10% of trades at −1.28R on average (p05 −2.54R, worst −7.3R). | Keep. Bound gap damage with the notional cap and the earnings exit. |
| A7 | Risk 1% per trade | 2% risk produced a lower CAGR (7.2% vs 7.7%) and a deeper drawdown (−37% vs −29%). | **Keep 1%.** Optionally 0.5% for the first 20 real trades (Q7). |
| A8 | Max 4 concurrent; no notional cap | Median notional is 32% of equity, so 4 slots don't fit in cash. Five slots × 20% gave 13.9% vs 11.9% (2021+) and 17.9% vs 13.5% (2014+). | **5 slots, 20% notional cap each,** and never more than available cash. |
| A9 | High SPY R² (≥0.70, 60d) → warn | Correlation with SPY is not a regime. It is warn-only noise and costs a second fetch. | **Delete.** Replace with a **regime gate**: no new entries while SPY's close is below its SMA(200). Evidence is mixed (2021+: 11.9% with the gate vs 9.4% without, drawdown −27% vs −34%; 2014+: 13.5% vs 16.8%). Default on as drawdown control; human call (Q3). |
| A10 | Earnings blackout T−2..T+1 around the entry day only | After this gate, 12.9% of trades still held through a report (2021+); the worst was −6.5R. Portfolio test: exiting before the report gave 7.7% vs 5.8% for holding. Safety and profit agree. | **Exit at the close of the session before the report date** (any time of day; conservative), via a market-on-close order. Skip entries with fewer than 3 sessions before that forced exit. Keep T+1 after the report as no-entry. |
| A11 | strict_earnings ON | Right for single stocks. Wrong for ETFs (no earnings), which halal universes often contain (SPUS, HLAL, UMMA). | Keep strict for `EQUITY`. Exempt `ETF` via `instrumentType` and show a note. Unknown type → treat as EQUITY. |
| A12 | strict_exdiv OFF; distribution ≥1% blocks | A long receives the dividend, so the ex-date drop is roughly neutral. The premium dividend endpoint is what caused the outage. | **Warn-only**, from yfinance `calendar` and dividend history. Never blocks, and is never required for `events_known`. |
| A13 | Liquidity = average dollar volume > 0 | That is no floor. Wide spreads and gaps hit thin names. | Price ≥ $5 and 20-day median dollar volume ≥ $10M (untested default; Q4). |
| A14 | ADR > 0 gate | Redundant with ATR > 0. | Delete. |
| A15 | Fill at next open; planned entry = signal close | Correct as a plan. A tight max-chase limit (0.25×ATR) **cost about 4–6 CAGR points** by skipping the strongest gap-ups. | Buy at the open with a market-on-open order, or a limit at signal close + 1.0×ATR as a catastrophe cap only. Size from the signal close. The harness must confirm the cap almost never binds. |
| A16 | Size = floor(1% × equity ÷ (1.5×ATR)) | Ignores cash, open positions and settlement. | `shares = min(risk_shares, floor(0.20 × equity ÷ price), floor(available_settled_cash ÷ price))`, where available cash = equity − Σ open cost basis − unsettled same-day sale proceeds. |
| A17 | Time stops not in v0 | A 10-session time stop cut expectancy (+0.049R vs +0.132R). The trailing stop plus earnings exit already bound holding time. | No time stop. |
| A18 | (absent) Benchmark | SPUS buy-and-hold (17.6%, 2021–26) beat every swing variant tested, including the best (13.9%). | Every report shows the **satellite vs SPUS** on the same capital. Ziad decides the core-satellite split (Q1). |

---

## 5. Challenges to providers and keys (including the Finnhub 403 fix)

### 5.1 Finnhub 403: root cause and remediation

**Root cause.** The key authenticates; `/stock/dividend` is Premium. A failed dividend call poisons `events_known`, so `EARNINGS_UNKNOWN` blocks every entry. The error hides the endpoint and body, so it looked like a key problem.

**Confirm on the Mac in 30 seconds, no code changes.** Run from the folder that holds `.env` (today: `~/halal-swing-cli/halal-swing-cli`):

```bash
set -a; source .env; set +a
curl -s -w "\nHTTP %{http_code}\n" -H "X-Finnhub-Token: $FINNHUB_API_KEY" \
  "https://finnhub.io/api/v1/calendar/earnings?symbol=AAPL&from=$(date +%F)&to=$(date -v+35d +%F)"
curl -s -w "\nHTTP %{http_code}\n" -H "X-Finnhub-Token: $FINNHUB_API_KEY" \
  "https://finnhub.io/api/v1/stock/dividend?symbol=AAPL&from=2026-01-01&to=2026-12-31"
```

Expected: the first call returns HTTP 200 with `earningsCalendar`; the second returns HTTP 403 `{"error":"You don't have access to this resource."}`. If the first returns 401, the key is mistyped (copy it again from the Finnhub dashboard). If the first returns 403, the account is restricted; regenerate the key or contact Finnhub support.

**Code fix (Phase 0).**

1. Delete the Finnhub dividend call.
2. Dividends come from yfinance, are optional, and never touch `events_known`.
3. The earnings window is today−5 to today+35 (inside the free tier).
4. HTTP errors carry the endpoint path and a redacted body snippet, for example `finnhub:/calendar/earnings:http_403:You don't have access to this resource.`
5. Errors are classified as `missing_key`, `invalid_key` (401), `plan_forbidden` (403), `rate_limited` (429), `upstream` (5xx/timeout), `bad_payload`, each with a one-line fix.

**Policy.** Earnings are known for an `EQUITY` when at least one source yields a next report date. Sources are Finnhub (if a key is set) and the yfinance calendar. The **earliest** date wins. Disagreement of more than 3 sessions shows `WARN_EARNINGS_DISAGREE`. If neither source yields a date, the result is `NO_TRADE EARNINGS_UNKNOWN` with fix steps: set `FINNHUB_API_KEY`, or check IBKR's calendar and pass `--earnings-date YYYY-MM-DD` for this run (the override is stamped on the plan).

### 5.2 Provider matrix (target)

| Need | Primary | Fallback / cross-check | On failure |
|---|---|---|---|
| Daily OHLCV (universe) | **Massive Basic** (`MASSIVE_API_KEY`, free): one grouped-daily call per session, plus a per-ticker backfill throttled to ≤5/min | yfinance one `history()` call, NaN tail rebuilt from 1-hour bars and flagged `reconstructed` | Ticker → `NO_TRADE DATA_STALE` with the source error and fix |
| Splits | Massive `/stocks/v1/splits` (one call per day for the universe) | yfinance `Stock Splits` column | Unexplained ≥40% move → `NO_TRADE DATA_SUSPECT` |
| Next earnings (EQUITY) | **Finnhub** `/calendar/earnings` (free key), window ≤35 days | yfinance `calendar` + `get_earnings_dates` (also gives the last report for T+1) | `NO_TRADE EARNINGS_UNKNOWN` + `--earnings-date` override |
| Instrument type | yfinance `history_metadata.instrumentType` | `[universe]` file column | Unknown → EQUITY (strict) |
| Ex-div date / amount | yfinance `calendar`, dividend history | — | No warning; never blocks |
| NYSE sessions | `exchange-calendars` (XNYS) | — | `NO_TRADE NO_NEXT_OPEN` |
| Regime | SPY (and optionally SPUS) from the same bar source | — | Unknown regime → no new entries |
| Benchmark | SPUS (default) or HLAL from the same bar source | — | Report shows "benchmark unavailable" |
| News | **removed** | — | — |

**Keys.**

- Recommended: `MASSIVE_API_KEY` (free) and `FINNHUB_API_KEY` (free).
- Removed: `CONTEXT_DEV_API_KEY`, `CONTEXT_DEV_BASE_URL`.
- Kept: `SWING_HOME` (replaces `SWING_DATA_DIR`), `SWING_CONFIG`.
- Optional, research only: a survivorship-free dataset (Sharadar SEP or EODHD) for the harness (Q9).

**Why not zero-key, given the profit priority.** Yahoo's NaN latest bar appears precisely in the Cairo pre-open window when decisions are made, and Yahoo rate-limits unpredictably. Official end-of-day data from a free key removes a class of missed or wrong trades. Setup friction is not a concern per Ziad.

---

## 6. Proposed target design (no code)

### 6.1 Daily workflow (Cairo)

The US regular session is 16:30–23:00 Cairo for most of the year, and 15:30–22:00 in the March/April and late-October shoulder weeks when only one country is on daylight time. The CLI prints both clocks.

1. **Morning (Cairo, after about 08:00):** run `swing today` (= `scan` + `positions`). It prints:
   - **Exits due today.** Market-on-close sells for positions whose pre-earnings exit date is today (NYSE MOC cutoff 15:50 ET).
   - **Ranked entries for today's open.** At most `free_slots`, each with an exact IBKR ticket: BUY market-on-open (or LMT at close + 1×ATR) for N shares, plus an OCA group of {STP at initial stop, TRAIL with a fixed amount}, all GTC.
   - **Capacity.** Free slots, available settled cash, open risk.
   - **Data status.** Source used per ticker, staleness, warnings.
2. Place the orders manually in IBKR before the open. The CLI never sends orders.
3. **After fills:** `swing buy TICKER --shares N --price P [--date]`. On exit: `swing sell TICKER --price P [--shares N]`. Both are append-only.
4. **Weekly:** `swing review` shows closed trades (R, win rate, expectancy ± standard error, average hold), satellite return vs SPUS on the same capital, forward-scored plans, and process adherence (fill vs plan).

### 6.2 Commands

| Command | Purpose |
|---|---|
| `swing scan [--json]` | Rank today's candidates across the universe; log `ENTER_LONG` plans to `plans.jsonl` |
| `swing today` | `scan` + exits due + capacity (the daily driver) |
| `swing analyze TICKER [--explain] [--json] [--earnings-date D]` | One-ticker detail view (same brain) |
| `swing buy` / `swing sell` / `swing positions` | Real fills (append-only book) |
| `swing review [--plans]` | Realized and forward-scored performance vs the benchmark |
| `swing backtest [--universe FILE] [--from D] [--variant NAME]` | Portfolio harness on the same brain code, with baselines |
| `swing doctor` | Live checks with fix steps (keys, endpoints, staleness, paths, book integrity) |

### 6.3 Module layout (target ≈1,800–2,300 src lines)

```
src/swing/
  cli.py            argparse subcommands; exit codes; no business logic
  config.py         SwingConfig (pydantic, extra=forbid, account.mode Literal["cash"]); config_hash
  home.py           SWING_HOME (~/.swing): config.toml, .env, universe.txt, book.jsonl, plans.jsonl, cache/
  data/
    http.py         get_json with endpoint+body in errors, error classification, throttling helper
    bars.py         BarSource protocol; massive.py, yfinance.py; sanitize(); freshness contract; fallback chain
    events.py       earnings (finnhub + yfinance merge, earliest wins), instrument type, ex-div (warn data)
    calendar.py     NYSE (as today)
    cache.py        per-ticker cache; never stores non-final bars
  brain/
    indicators.py   as today (SMA, EMA, Wilder RSI/ATR) + momentum
    triggers.py     bo_rvol, pb_ema, rsi2 (pure functions)
    rules.py        gates → Candidate | NoTrade(reason); sizing; exit plan (stops, trail, earnings exit date)
    portfolio.py    rank candidates, allocate free slots under cash; pure, used by scan AND backtest
  book.py           book.jsonl (fills) + plans.jsonl (auto plans); open positions; available cash
  report.py         card, --explain, --json (schema 2.0.0); review tables
  backtest.py       day loop over cached bars calling brain.rules + brain.portfolio; baselines; metrics
  doctor.py
```

**Deleted:** `research/` (5 files), `broker/`, `brain/stub.py`, `brain/gates.py` (folded into `rules.py`), `brain/positions.py` (into `book.py`), `guards.py`, `disclaimer.py` (into `report.py`), `data/ports.py`, `data/factory.py`, `data/corp_actions.py`, `data/finnhub.py` dividend code, `envelope.py` (replaced by schema 2.0 models in `report.py`), unused codes in `codes.py`.

### 6.4 Algorithm v1 (defaults = config; every number hashed into `config_hash`)

For each ticker in `universe.txt` (Ziad's screened list; required file):

1. **DATA.** At least 260 sessions, sanitized; the last bar equals the last completed NYSE session.
2. **INSTRUMENT.** `EQUITY` or `ETF` (from metadata or the universe file).
3. **LIQUIDITY.** Close ≥ $5 and 20-session median of close × volume ≥ $10,000,000.
4. **NOT HELD.** The ticker is not an open position in `book.jsonl`.
5. **REGIME** (portfolio-level). SPY close > SMA(200), else no new entries (`regime.gate=true`).
6. **TREND.** Close > SMA(200).
7. **TRIGGER.** Any of the following (labels recorded):
   - BO_RVOL: close > SMA(50), close > prior 20-session high, volume ≥ 1.5 × prior 20-session average volume;
   - PB_EMA: close > EMA(50), low ≤ EMA(20) < close;
   - RSI2: Wilder RSI(2) < 10.
8. **EARNINGS** (EQUITY only). The next report date E must be known. The forced exit is the close of the session before E, and it must be at least 3 sessions after the entry session. No entry on the session right after a report (T+1). ETFs skip this gate with a note.
9. **PLAN.**
   - ATR = ATR(14), Wilder.
   - `stop = close − 1.5·ATR`; `trail_amount = 3.0·ATR` (fixed $, set at entry).
   - `entry_cap = close + 1.0·ATR` (limit, or market-on-open).
   - `risk_shares = floor(0.01·equity ÷ (close − stop))`.
   - `shares = min(risk_shares, floor(0.20·equity ÷ entry_cap), floor(available_cash ÷ entry_cap))`; fewer than 1 share → `NO_TRADE SIZE_BELOW_ONE_SHARE`.
   - The plan includes `exit_by` (forced exit date) and ex-div warnings.
10. **RANK** (portfolio). Momentum = close[t−5] ÷ close[t−126] − 1, descending. Allocate `free_slots = 5 − open_positions`, skipping any candidate that cannot be funded.

**Exits** (printed for IBKR; tracked by `swing positions`): the initial STP, the TRAIL order (OCA with the STP), and a market-on-close order on `exit_by`. No fixed target and no time stop by default. `exit.mode = "trail"` is the default and `"target_2r"` is selectable, so Q2 is a config edit, not code.

**Config surface (v1):**

- `account.equity_usd`, `account.mode="cash"`
- `risk.per_trade=0.01`
- `portfolio.slots=5`, `portfolio.max_position_frac=0.20`
- `regime.gate=true`, `regime.symbol="SPY"`, `regime.sma=200`
- `trend.sma=200`
- `triggers.enabled=["BO_RVOL","PB_EMA","RSI2"]` plus their parameters
- `rank.lookback=126`, `rank.skip=5`
- `stops.atr_period=14`, `stops.initial_atr=1.5`
- `exit.mode="trail"`, `exit.trail_atr=3.0`, `exit.target_r=2.0`
- `entry.cap_atr=1.0`
- `earnings.strict=true`, `earnings.min_room_sessions=3`, `earnings.after_days=1`
- `liquidity.min_price=5`, `liquidity.min_median_dollar_volume=10_000_000`
- `benchmark.symbol="SPUS"`
- `timezone.user="Africa/Cairo"`

### 6.5 Book and plans (append-only, JSONL)

- `book.jsonl` events:
  - buy: `{schema:"2", type:"buy", ticker, shares, price, date, stop, trail_amount, exit_by, plan_id, config_hash}`
  - sell: `{type:"sell", ticker, shares, price, date, reason}`, where reason ∈ `stop|trail|earnings|manual`
  Open = Σ buys − Σ sells per ticker. A malformed line stops the command (as today) with the line number.
- `plans.jsonl`: every `ENTER_LONG` from scan or analyze, deduplicated on `(ticker, signal_session, config_hash)`. `review --plans` replays each plan forward on cached bars with the same exit rules, giving free forward evidence without placing trades.
- **Migration:** v0 `journal.jsonl` lines are *plans*. Archive the file as `journal.v0.jsonl` and import it into `plans.jsonl`. Import nothing into the book unless Ziad confirms real fills (Q10).

### 6.6 Output

The default card per actionable ticker shows:

- the ticker and rank;
- triggers matched and momentum;
- the IBKR ticket lines (BUY qty and type; STP; TRAIL amount; OCA; GTC);
- risk in $ and % equity, notional in $ and % equity;
- the `exit_by` date with its reason;
- data source and as-of session;
- a one-line disclaimer.

Non-actionable tickers get one line: the reason in plain words plus the fix if it is a data or key problem. `--explain` adds every gate and number. `--json` emits schema 2.0.0: `decision`, `reasons`, `warnings`, `plan`, `data`, `config_hash`, `shariah:{screened:false, source:"user_universe"}`, `disclaimer`.

---

## 7. Phased implementation plan (for the next chat)

General rules for every phase:

- One logical change per commit; push to `main` (Ziad's preference; no PRs).
- `uv run pytest` green and offline at every commit. Network only in `doctor`, `scan`, `analyze` and `backtest` at runtime, never in tests.
- macOS is the runtime, the VM is Linux. Inject `platform`/`home` in path tests and never hardcode `/Users/...`.

### Phase 0: Correctness hotfix (unblocks real decisions; smallest diff; ship first)

1. Remove the Finnhub `/stock/dividend` call. Dividends become optional and come from the yfinance calendar or history. A dividend failure never changes `events_known`.
2. Shrink the Finnhub earnings window to today−5 .. today+35.
3. `http.get_json`: include the endpoint path and a redacted body snippet (≤200 chars) in `VendorError`; classify 401/403/429/5xx.
4. yfinance: a single `history()` call (auto-adjusted, actions on). Drop rows with non-finite or non-positive OHLC (no NaN→0). Drop sessions after `last_completed_session(now)`. If the last remaining session ≠ last completed, rebuild it from 1-hour regular-hours bars (keep the daily row's volume) and flag `reconstructed`; if that fails → `NO_TRADE DATA_STALE`. Never write a non-final or reconstructed bar to the cache.
5. Earnings fallback: when Finnhub is missing or fails, use the yfinance `calendar` and `get_earnings_dates`. ETF (`instrumentType`) → earnings gate passes with a note.
6. `analyze` stops appending to the journal (the plan still prints). The CLI tells the user how to archive an existing `journal.jsonl` if `MAX_POSITIONS` is caused by old plan lines.

*Acceptance:*

- Unit tests with fixtures: Finnhub earnings 200 + dividend 403 → `events_known=True` and no 403 in errors. A NaN tail bar is dropped and never cached. A partial intraday bar is ignored. A stale last bar → `DATA_STALE`. An ETF passes the earnings gate. Error strings contain the endpoint and status class.
- On the Mac in the Cairo morning: `swing analyze AAPL --equity 10000` returns a checklist decision (not `EARNINGS_UNKNOWN` and not `CORP_ACTION_SUSPECT`) with only the free Finnhub key, and also with no key.

### Phase 1: Delete dead weight (pure removal; behaviour unchanged except removed features)

1. Delete `research/` and the Context.dev keys from `.env.example` and docs.
2. Delete `broker/`, `brain/stub.py`, `data/ports.py`, the `inspect.signature` adapter, `guards.py` (make `account.mode` `Literal["cash"]`), the reserved Shariah codes, the `BLOCK` decision, the SPY R² warning and its SPY fetch, the ADR gate, `--compact` and `--simple` (the card becomes the default output).
3. Replace prose-asserting tests with behaviour tests.

*Acceptance:* tests green; the `src` line count drops by at least 500 (whole-file deletions alone are about 370 lines); `swing analyze` output still carries decision, plan, reasons, `config_hash` and disclaimer; a lock test asserts no broker or order library is in `uv.lock` and no `ENTER_SHORT` exists.

### Phase 2: Data layer for a universe

1. `home.py`: `SWING_HOME` defaults to `~/.swing`, holding `config.toml`, `.env`, `universe.txt`, the book, plans and cache. One-time migration from `~/Library/Application Support/swing` (copy, never delete).
2. Massive provider: one grouped-daily call per missing session for the whole universe, a per-ticker backfill (2 years) throttled at ≤5 calls/min with a progress line, and the splits list once per day. Remove the raw-aggs and dividends calls.
3. Fallback chain per ticker: Massive → yfinance (Phase 0 rules) → `DATA_STALE`.
4. `events.py`: Finnhub + yfinance merge, earliest wins, `WARN_EARNINGS_DISAGREE`, last-report date for T+1, the `--earnings-date` override.
5. Delete `corp_actions.py` and use `sanitize()` plus the split list. Flag an unexplained ≥40% move.

*Acceptance:* fixture tests for grouped-daily parsing, throttling (fake clock), fallback ordering, the earnings merge (earliest wins, disagreement warning), ETF exemption, override stamping. A cold scan of 30 tickers completes within the throttle budget; a warm scan makes ≤3 HTTP calls in total.

### Phase 3: Measurement harness (before changing the algorithm)

1. `brain/portfolio.py`: a pure ranking and slot allocator used by both `scan` and `backtest`.
2. `swing backtest`:
   - a day loop over cached bars;
   - signals at close t, fills at open t+1 (with the entry cap);
   - exits in order: gap-through stop at open → stop → trail update after the bar → MOC on `exit_by`;
   - costs of IBKR minimum commission plus 5 bps per side;
   - cash ledger with T+1 settlement;
   - metrics: CAGR, max drawdown, Sharpe, % time invested, trades/yr, mean R ± standard error, worst trade % equity, share of trades losing more than 1.5% of equity.
3. Built-in baselines in every report: (a) the same rules with random ranking (fixed seed), (b) v0 rules, (c) buy-and-hold of the benchmark and SPY.
4. Pre-registered variants only (Appendix A list). **No parameter grid search.**
5. Optional adapter for a survivorship-free dataset (Q9).

*Acceptance:* on the same 50-ticker yfinance sample the harness reproduces the Appendix A orderings that drive the design: D2 > J (ranking), I > D2 (slots), D2 > M (trail vs 2R), C > E (earnings exit), D2 > H (no tight chase). With the Appendix A cost and settlement assumptions, CAGR lands within ±2 points of Appendix A. Determinism: the same inputs give identical output. It uses the same `rules.py` functions as `scan` (a test asserts identical candidates on a fixture day).

### Phase 4: Algorithm v1

1. Implement Section 6.4: trend filter on all triggers, mutex removed, momentum rank, regime gate, earnings exit, slots and cap, cash constraint, initial stop + fixed trail (or 2R by config), liquidity floor, entry cap. Remove the heat and sector configs.
2. Ship only if the harness on the best available data shows v1 ≥ v0 on CAGR **and** Sharpe in both windows, and v1 beats its random-rank baseline. Otherwise stop and report to Ziad with the tables; do not tune parameters to pass.

*Acceptance:* unit tests for each gate and sizing branch; plan arithmetic golden tests; the harness comparison table committed under `docs/backtests/` as markdown.

### Phase 5: Portfolio product

1. `book.py` with `swing buy`, `swing sell` and `swing positions` (open risk, notional, unrealized R, `exit_by`, actions due).
2. `plans.jsonl` auto-logging and dedupe; `swing review --plans` forward scoring.
3. `swing today`; `swing review` vs the benchmark (satellite capital-weighted return vs the benchmark over the same dates).
4. Archive and import the v0 journal.

*Acceptance:* append-only invariants tested (no rewrite; a malformed line refuses with its line number); available cash accounts for open cost basis and unsettled same-day sales; an `ALREADY_OPEN` ticker is never re-planned; the review math is checked against a hand-computed fixture.

### Phase 6: Ops and setup (lowest priority per Ziad)

1. `swing doctor`: Python and install path; which `.env` files loaded and which key names, masked; live probe of each configured endpoint the CLI actually calls (classified with fix lines); bars freshness for SPY; universe file; book integrity; nested-clone warning (CWD has a child `halal-swing-cli/pyproject.toml` but no `pyproject.toml` of its own).
2. A short README covering: `uv tool install --editable .` (the `swing` command available everywhere), `~/.swing` layout, the daily workflow, and an IBKR order-ticket walkthrough.
3. `docs/architecture.md` rewritten; ADR 0002 records this redesign and supersedes the prefs table.

### What NOT to do (all phases)

- Do not place, route or stage orders; no IBKR API, `ib_insync`/`ib_async`, TWS or Client Portal calls.
- Do not add shorts, margin, options, CFDs, futures, FX or non-USD.
- Do not call Finnhub premium endpoints (`/stock/dividend`, `/stock/dividend2`, `/stock/candle`, `/stock/split`) or add any vendor without a documented free or paid tier decision.
- Do not add Zoya or any Shariah screening, ruling, or certification wording; the universe file is the user's screen.
- Do not let news, LLM output or sentiment touch decisions.
- Do not grid-search or tune parameters on the backtest. Variants are pre-registered and use round numbers.
- Do not coerce NaN or missing prices to 0, and do not treat an empty earnings list as "no earnings" unless at least one source returned a dated next report or a full-window response.
- Do not weaken strict earnings for single stocks to make trades appear.
- Do not delete or rewrite user data files; migrations copy and archive.
- No network in tests.
- No database, web UI, daemon, scheduler, notifications, or GUI.

---

## 8. Open questions for Ziad (need a human call)

1. **Core-satellite.** SPUS buy-and-hold beat every tested swing variant over 2021–26. Do you want a fixed core (for example 50% in SPUS or HLAL, held, not managed by the CLI) plus a swing satellite sized by `account.equity_usd`? Or 100% swing? The CLI reports satellite vs benchmark either way.
2. **Exit style.** Trailing 3×ATR (higher CAGR in tests, ~35–39% win rate, deeper drawdowns) or fixed 2R target (higher win rate, lower CAGR)? Default: trailing.
3. **Regime gate.** Hard no-new-entries below SPY's SMA200 (default), half size, or off? Evidence is mixed.
4. **Liquidity floor.** $10M 20-day median dollar volume and $5 minimum price; is that suitable for your screened universe (some halal names are small)?
5. **Slots.** Five at 20% (default) or four at 25%?
6. **Entry order.** Market-on-open, or limit at close + 1×ATR (default)?
7. **Probation.** Risk 0.5% per trade for the first 20 real trades, then 1%?
8. **Earnings.** Confirm "never hold through a report" for single stocks (default), and that using the day before the report date regardless of time of day is acceptable.
9. **Research data.** Pay for survivorship-free data (Sharadar SEP or EODHD, which work from macOS) to validate the edge honestly? Norgate needs Windows.
10. **v0 journal.** Were any `journal.jsonl` lines real IBKR fills? If yes, they will be imported into the book; otherwise they are archived as plans.
11. **IBKR account type.** Is it a **Cash** account (not Reg T margin)? The CLI caps by cash either way, but a margin account would let a manual typo borrow.
12. **Account size.** Roughly what equity? At $10k, IBKR Pro Fixed's $1 minimum per order costs about 1.2–1.6% a year at 60–80 round trips. Tiered pricing ($0.35 minimum plus fees) may be cheaper; check in IBKR.
13. **Universe.** How many tickers, and do they include ETFs? Ranking needs roughly 20 or more names to be meaningful.
14. **Keys.** OK to require the free Massive and Finnhub keys and drop Context.dev entirely?
15. **Home folder.** `~/.swing` (no spaces, survives re-clones) instead of `~/Library/Application Support/swing`?

---

## 9. Success metrics (honest and measurable)

**Profit (primary; none of these is promised):**

- **P1. Harness gate.** v1 beats v0 and its own random-rank baseline on CAGR and Sharpe, in both windows, on the best available data. Measured by `swing backtest`; reported tables live in `docs/backtests/`.
- **P2. Live alpha.** Satellite return on deployed capital minus SPUS over the same dates, after costs, reported by `swing review`. It is "proven" only when mean trade R minus 2 standard errors is above 0 after at least 100 closed trades **and** satellite return beats the benchmark over at least 12 months. Until then the review prints "unproven".
- **P3. Forward plans.** Scored-plan expectancy (mean R ± standard error) tracked weekly. If it is below 0 after 100 or more scored plans, `review` flags the rule set.

**Capital protection (enforced in code, tested):**

- **S1.** Planned open notional is never above available settled cash; tested invariant.
- **S2.** Zero single-stock positions held through a known report (book audit in `review`).
- **S3.** At least 99% of closed trades lose at most 1.5% of equity; worst at most 2.5%. Smoke reference (Appendix A.2): v0 had 3.2% of trades worse than −1.5% and a worst of −6.46%; the cap + earnings-exit rules alone brought that to 1.05% and −2.89%. v1's own figure must come from the Phase 3 harness.
- **S4.** Satellite maximum drawdown at most the benchmark's over the same window (reported).

**Product correctness:**

- **C1.** Zero spurious vendor-caused `NO_TRADE` results on trading days over a two-week Cairo-morning trial (`review` tallies reasons from `plans.jsonl` and scan logs).
- **C2.** Warm `swing today` on 30 tickers in under 15 s with at most 3 HTTP calls; cold backfill within the throttle budget.
- **C3.** `swing doctor` classifies missing key, 401, 403 (with endpoint), 429, stale bars, NaN bars and a malformed book, each with a fix line (fixture tests).
- **C4.** Process adherence: median |fill − planned entry| at most 0.1R, and the IBKR ticket matches the plan (fields compared in `review`).

**Ease of setup (tracked, not optimized):** a fresh Mac reaches a first `swing today` in at most 6 commands.

---

## Appendix A: Smoke-test method and results

**Data and assumptions.**

- Universe: 50 current large caps — AAPL MSFT NVDA AMZN GOOGL META AVGO TSLA COST PEP KO PG JNJ MRK ABBV LLY UNH HD LOW MCD NKE TXN QCOM AMD INTC CSCO ORCL ADBE CRM ACN CAT DE HON UNP LIN TMO DHR ISRG AMGN GILD XOM CVX COP SLB NEE DUK WMT TGT SBUX BKNG — plus SPY and SPUS.
- Bars: yfinance auto-adjusted daily, 2013-01-01 → 2026-10-01. Indicators match the repo definitions; pandas EMA seeding differs slightly.
- Earnings dates: yfinance `get_earnings_dates(limit=60)`, reliable from 2020, so earnings-dependent variants use 2021+.
- Fills at the next open; stop gap fills at the open; costs 5 bps per side plus $1 per order; $100k start for portfolio runs.

**Biases.** This is a survivorship-biased universe (today's winners), which inflates momentum ranking most. It is a single price path, there is no point-in-time halal universe, and there are no taxes. Treat the numbers as ordering evidence only.

**A.1 Per-trade, same 1.5×ATR stop / 2R target, one trade per ticker at a time (2013–2026)**

| Entry rule | n | mean R | SE | win % | median hold |
|---|---|---|---|---|---|
| v0 setups (mutex) | 7,346 | +0.133 | 0.018 | 39.5 | 8 |
| Random day (20% sample) | 9,569 | +0.164 | 0.016 | 40.5 | 8 |
| Random, close > SMA200 | 6,948 | +0.142 | 0.019 | 39.8 | 8 |
| Random, SMA50 > SMA200 | 4,824 | +0.128 | 0.022 | 39.3 | 8 |
| Random, within 5% of 52-week high | 3,884 | +0.126 | 0.025 | 39.2 | 8 |

Exit variants on v0 entries: stop/2R +0.132R; 10-session time stop +0.049R; close > SMA(5) exit −0.012R.

v0 risk facts:

- Notional: median 31.8% of equity; 72% of trades above 25%; 10% above 50%.
- Stop gaps: 10% of trades, mean −1.28R, p05 −2.54R, worst −7.27R.
- Next-open vs signal close: p05 −0.43R, p95 +0.45R.
- Earnings (2021+): 12.9% of trades passing the current gate still held through a report; worst −6.51R.

**A.2 Per-trade % of equity, 2021+**

| Rules | n | mean % eq | worst % eq | share losing > 1.5% eq |
|---|---|---|---|---|
| v0 | 3,188 | +0.068 | −6.46 | 3.23% |
| v0 + 25% notional cap | 3,188 | +0.055 | −4.97 | 1.88% |
| v0 + cap + earnings exit | 3,238 | +0.065 | −2.89 | 1.05% |
| RSI2 + regime + cap + earnings exit + 0.25×ATR chase | 1,236 | +0.044 | −1.65 | 0.24% |

**A.3 Portfolio level, cash-constrained, 4 slots unless noted (2021-01-04 → 2026-09-30)**

| Variant | CAGR % | Max DD % | Sharpe | trades/yr |
|---|---|---|---|---|
| SPUS buy-and-hold | 17.61 | −28.22 | 0.95 | – |
| SPY buy-and-hold | 15.07 | −24.50 | 0.93 | – |
| A: v0 triggers, random order, 2R, no cap | 3.40 | −28.29 | 0.29 | 94 |
| B: RSI2 + regime + 25% cap + earnings exit + 0.25×ATR chase, 2R | 6.80 | −17.49 | 0.67 | 74 |
| C/M: all triggers + momentum rank + regime + 25% cap + earnings exit, 2R | 7.71 | −28.73 | 0.58 | 88 |
| D2: as C with fixed 3×ATR trail instead of 2R | 11.93 | −26.88 | 0.79 | 63 |
| **I: D2 with 5 slots × 20%** | **13.90** | −26.39 | **0.87** | 79 |
| J: D2 with random rank | 2.98 | −21.49 | 0.29 | 65 |
| K: D2 without regime gate | 9.44 | −34.25 | 0.59 | 75 |
| L: D2 RSI2-only | 4.46 | −26.35 | 0.39 | 59 |
| H: D2 + 0.25×ATR max chase | 7.47 | −18.37 | 0.60 | 66 |
| E: C holding through earnings | 5.78 | −27.49 | 0.44 | 81 |
| G: C at 2% risk | 7.20 | −37.10 | 0.46 | 88 |

**A.4 Portfolio level, 2014-06-02 → 2026-09-30** (no earnings rule: dates unavailable before 2020; SPUS starts in Dec 2019)

| Variant | CAGR % | Max DD % | Sharpe |
|---|---|---|---|
| SPY buy-and-hold | 13.73 | −33.72 | 0.83 |
| A: v0 | 11.70 | −23.13 | 0.79 |
| D2: momentum + trail | 13.50 | −38.61 | 0.85 |
| **I: D2, 5 × 20%** | **17.88** | −33.99 | **1.03** |
| J: random rank | 8.54 | −26.33 | 0.66 |
| K: no regime | 16.78 | −33.58 | 0.93 |
| L: RSI2-only | 12.96 | −32.50 | 0.88 |
| M: 2R target | 12.04 | −27.54 | 0.81 |
| H: 0.25×ATR chase | 7.05 | −25.91 | 0.56 |

**Pre-registered variant list for the Phase 3 harness:** A, B, C/M, D2, I, J, K, L, H, E, G as defined above, plus "I with market-on-open (no entry cap)" and "I with a 1×ATR entry cap".

## Appendix B: Paths and platform notes

- **Product (macOS):** proposed `~/.swing/` with `config.toml`, `.env` (chmod 600), `universe.txt`, `book.jsonl`, `plans.jsonl`, `cache/`. v0 used `~/Library/Application Support/swing/`; Phase 2 migrates by copying.
- **Current footgun:** the real project lives at `~/halal-swing-cli/halal-swing-cli` inside an empty outer git folder. With `uv tool install --editable .` from the inner folder and keys in `~/.swing/.env`, the working directory stops mattering. `doctor` warns when run from the outer folder.
- **This review ran on Linux** (`~/.local/share/swing` fallback). Path code must keep platform and home injection for tests. Cairo DST (Egypt reinstated it in 2023) comes from the system tz database on macOS.

---

## IMPLEMENTATION PROMPT

Paste the block below into a new chat (Opus 5.5 Extra High) opened on `ZiadMohamed/halal-swing-cli`.

```text
You are implementing the redesign in docs/REDESIGN_PLAN.md of the private repo ZiadMohamed/halal-swing-cli
(personal macOS CLI, Python 3.12 + uv). Read docs/REDESIGN_PLAN.md fully before writing code; it is the spec.
Where this prompt and the plan disagree, the plan's Section 7 wins.

Priorities (set by Ziad): profit and product first; capital protection is enforced; ease of setup is last.

Hard product locks (never change):
- Cash account, long equity/ETF only, USD only. No shorts, margin, options, CFDs, futures, FX.
- The CLI never places, routes, or stages orders. No IBKR API libraries. Ziad types orders in IBKR.
- Ziad supplies the screened universe (~/.swing/universe.txt). No Zoya/Shariah screening, no rulings,
  no certification wording. Keep "Not financial advice. Not a Shariah certification."
- Never plan a purchase larger than available settled cash.

Git: work on main, one commit per logical change, descriptive messages, push to origin main after each phase
(Ziad's preference: no PRs). Never force-push. Keep `uv run pytest` green and offline at every commit.
macOS is the runtime; you may be on Linux: inject platform/home in path tests, never hardcode /Users paths.

Execute phases in order, stopping at each phase's acceptance criteria:
Phase 0 Correctness hotfix: drop Finnhub /stock/dividend (premium → the 403); dividends optional via yfinance
  and never affect events_known; Finnhub earnings window today-5..today+35; VendorError carries endpoint + redacted
  body + status class (401 invalid_key, 403 plan_forbidden, 429 rate_limited, 5xx upstream); yfinance single
  history() call, drop non-finite/non-positive OHLC (never NaN→0), drop sessions after last completed NYSE session,
  rebuild a missing last session from 1h regular-hours bars (flag reconstructed, keep daily volume) else DATA_STALE,
  never cache non-final/reconstructed bars; yfinance earnings fallback (calendar + get_earnings_dates);
  ETF via history_metadata.instrumentType skips earnings; analyze stops appending to the journal.
Phase 1 Delete: research/ (Context.dev), broker/, brain/stub.py, data/ports.py, inspect.signature adapter,
  guards.py (account.mode Literal["cash"]), reserved Shariah codes, BLOCK decision, SPY R² warn + SPY fetch,
  ADR gate, --compact/--simple (card is default; keep --json, add --explain); replace prose-asserting tests.
Phase 2 Data for a universe: SWING_HOME=~/.swing (copy-migrate from ~/Library/Application Support/swing);
  Massive grouped-daily (1 call/session for the universe) + throttled per-ticker backfill (≤5/min) + daily splits;
  remove raw-aggs/dividends calls; fallback Massive→yfinance→DATA_STALE; earnings merge Finnhub+yfinance,
  earliest wins, WARN_EARNINGS_DISAGREE, --earnings-date override stamped on plans; replace corp_actions.py
  with sanitize() + split list + ≥40% unexplained-move flag.
Phase 3 Measurement harness BEFORE changing rules: brain/portfolio.py (pure rank + slot allocation shared by scan
  and backtest); `swing backtest` day loop (signal at close t, fill at open t+1, gap-through stops, trail update
  after bar, MOC on exit_by, IBKR min commission + 5 bps/side, T+1 cash ledger), metrics (CAGR, maxDD, Sharpe,
  %invested, trades/yr, mean R ± SE, worst trade %eq, share of trades losing >1.5% eq), built-in baselines
  (random rank seeded, v0 rules, SPUS and SPY buy-and-hold). Only the pre-registered variants in Appendix A.
  NO parameter grid search. On the same 50-ticker yfinance sample it must reproduce the Appendix A orderings
  D2>J, I>D2, D2>M, C>E, D2>H, and CAGR within ±2 points under the Appendix A cost/settlement assumptions.
Phase 4 Algorithm v1 (Section 6.4 exactly): trend filter close>SMA200 on all triggers; triggers BO_RVOL/PB_EMA/RSI2
  any-of (no mutex); regime gate SPY>SMA200 (config); EQUITY earnings rule: forced exit at close of session
  before report date, ≥3 sessions room, no entry at T+1; liquidity ≥$5 and ≥$10M 20d median dollar volume;
  rank by close[t-5]/close[t-126]-1; 5 slots, 20% notional cap, 1% risk from 1.5×ATR initial stop, cash cap;
  exit.mode="trail" (fixed 3×ATR TRAIL in OCA with the STP) default, "target_2r" selectable; entry cap close+1×ATR.
  Ship only if the harness shows v1 ≥ v0 on CAGR AND Sharpe in both windows and v1 beats its random-rank baseline;
  otherwise stop and report tables to Ziad without tuning. Commit the comparison table under docs/backtests/.
Phase 5 Portfolio product: book.jsonl (buy/sell fills, append-only) + plans.jsonl (auto, deduped on ticker+signal
  session+config_hash), swing buy/sell/positions/today/review (satellite vs SPUS, forward-scored plans,
  "unproven" until mean R − 2·SE > 0 after ≥100 closed trades); archive v0 journal.jsonl as journal.v0.jsonl and
  import as plans only.
Phase 6 Ops (lowest priority): swing doctor (live endpoint probes with fix lines, masked key sources, freshness,
  nested-clone warning), short README (uv tool install --editable ., ~/.swing layout, daily Cairo workflow,
  IBKR ticket walkthrough), rewrite docs/architecture.md, add ADR 0002.

Defaults pending Ziad's answers (plan Section 8) must be config values, not code branches: exit.mode, regime.gate,
portfolio.slots / max_position_frac, liquidity floors, entry.cap_atr, risk.per_trade, benchmark.symbol.

Do NOT: call Finnhub premium endpoints; add vendors beyond Massive/Finnhub/yfinance (Tiingo, Sharadar, EODHD only
if Ziad says so); let news/LLM/sentiment affect decisions; coerce NaN to 0; treat an empty earnings list as clear
without a dated next report; weaken strict earnings for single stocks; rewrite or delete user data files;
use network in tests; add a database, web UI, daemon, scheduler, or notifications; claim edge in output text.

When done with each phase: run tests, commit, push to main, and post a short summary with what changed, test
results, and any acceptance criterion you could not meet (with the reason).
```
