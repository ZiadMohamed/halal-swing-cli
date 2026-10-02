# Section 8 answers

Date: 2026-10-02
Status: accepted as operator and future-config defaults
Spec: `docs/REDESIGN_PLAN.md` Section 8, Section 6.4, and Phase 4
Evidence: `docs/backtests/v1-gate.md`, `docs/backtests/appendix-a-reproduction.md`, Appendix A of the redesign plan

This file records one default for each open question. It does not retune the backtest, does not change the live checklist, and does not make a Shariah ruling. The universe file remains the user's screen. SPUS and HLAL appear only as examples the plan already used. SPY remains a timing series, not a holding.

## Live checklist stays on v0

Leave the live checklist on v0.

The ship rule in Phase 4 requires v1 to beat v0 on CAGR and Sharpe in both windows, and to beat its own random-rank book on those same metrics. `docs/backtests/v1-gate.md` (no parameter changed after the run):

| Window | Book | CAGR % | Sharpe | Max DD % |
|---|---|---:|---:|---:|
| 2021-01-04 → 2026-09-30 | v0 | −9.93 | −0.73 | −49.45 |
| 2021-01-04 → 2026-09-30 | v1 | 13.67 | 0.96 | −22.15 |
| 2021-01-04 → 2026-09-30 | v1 random rank | 4.96 | 0.50 | −18.52 |
| 2014-06-02 → 2026-09-30 | v0 | 5.86 | 0.50 | −30.20 |
| 2014-06-02 → 2026-09-30 | v1 | 12.74 | 0.90 | −24.43 |
| 2014-06-02 → 2026-09-30 | v1 random rank | 10.55 | 0.95 | −21.89 |

v1 beats v0 on CAGR and Sharpe in both windows. v1 beats random rank on CAGR in both windows and on Sharpe in 2021 (0.96 vs 0.50). In the 2014 window the random-rank Sharpe is higher (0.95 vs 0.90). That fails the rule. ADR 0002 already records the same call.

Outside research does not overturn the miss. Cross-sectional momentum is a real published effect, and it is also the effect a survivor list inflates most. The harness universe is today's large caps (Appendix A). Earnings are off before 2020. The reproduction missed several Appendix A CAGRs by more than 2 points, including the no-regime book K in 2021 (reproduced 15.51 vs appendix 9.44). A 0.05 Sharpe gap on one biased window is not a reason to ship, and it is not a reason to search parameters until the gap flips.

Do not retune trail width, slot count, the regime gate, the rank window, or the entry cap to force a pass. The next live-book change needs a new harness run on the best available data, with the same pre-registered rule.

## What a follow-up may change

Three layers:

1. **Live checklist (`ChecklistBrain`, `SwingConfig` built-in defaults).** Leave these numbers as they are. v0 still uses the mutex, the 2R target, four positions, the entry blackout, and `risk.per_trade = 0.01`.
2. **Operator file `~/.swing/config.toml`.** The user may set equity and a temporary half-size risk here. That file is not in git.
3. **v1 config surface (Section 6.4).** Record the values below as the defaults for a future book. They already match `VARIANTS["v1"]` in `src/swing/backtest.py`. Do not point `swing analyze` at that variant.

Any new key that later lands on `SwingConfig` has to be included in `config_hash`. Until a passing gate, `ChecklistBrain` does not read the v1-only keys.

## Q1. Core-satellite

**Default:** core-satellite. The CLI manages the satellite only. Starting split **80% core / 20% satellite**. `account.equity_usd` is the satellite sleeve in USD, not total net worth. The core is held outside the CLI in a USD equity ETF already on the user's screened list. The plan's examples are SPUS and HLAL. `benchmark.symbol` stays `"SPUS"` when the core is SPUS. If the core is a different screened ETF, set `benchmark.symbol` to that ticker so `swing review` compares the sleeve with the core actually held.

**Confidence:** high on using a core; medium on the 20% starting weight.

**Why:** On the 2021 window, SPUS buy-and-hold CAGR was 17.61% in Appendix A and 17.24% in the reproduction. The best swing book in those tables was lower (Appendix I 13.90%; v1 13.67%). Published core-satellite practice keeps the indexed core as the majority and sizes the active sleeve at about 10–30% until the investor has shown skill. A 60/40 split is the aggressive end of the retail examples, and a 10% active tilt is a common professional starting cap. Twenty percent is the middle of the usual satellite band and matches an unproven sleeve (success metric P2 needs 100 closed trades and 12 months). One hundred percent swing would put the whole account in a book that lost the ship gate and lost to the screened buy-and-hold.

The core also makes the hard regime gate (Q3) tolerable: below SPY's SMA(200) the satellite goes to cash and the core stays invested.

**Watch:** the sleeve's commission drag (Q12). A 20% sleeve on a small account can be too small for 60–80 round trips a year. Raise the satellite weight only after P2 prints a proven sleeve. Rebalance the sleeve back to its weight if it grows. This note does not rank SPUS against HLAL.

**Sources:** [Saxo core-satellite](https://www.home.saxo/learn/guides/diversification/core-satellite-approach-a-smarter-way-to-diversify-your-investments) (80/20 conservative, 70/30 balanced, 60/40 aggressive), [CFA Institute, 10% active starting cap](https://rpc.cfainstitute.org/blogs/enterprising-investor/2012/simple-safe-and-cost-effective-using-a-coresatellite-approach-in-your-401k-2), [Vanguard core-satellite paper](https://foro.masdividendos.com/uploads/short-url/rbMi96R83iOwRmFBgugMs0nOmzv.pdf) (majority indexed unless manager-selection skill is essentially perfect), [Vanguard Australia](https://www.vanguard.com.au/personal/learn/smart-investing/investing-strategy/core-satellite-investing).

## Q2. Exit style

**Default:** `exit.mode = "trail"`, `exit.trail_atr = 3.0`, with `stops.initial_atr = 1.5` and `stops.atr_period = 14`. `exit.target_r = 2.0` stays selectable and is not the default. No time stop.

**Confidence:** medium.

**Why:** A fixed target caps the right tail. Volatility trails are the usual exit for trend and momentum books; a fixed target fits a bounded mean-reversion bet. The standard Chandelier exit is about 3×ATR. Appendix A: the 3×ATR trail (D2) CAGR was 11.93% vs 7.71% for the 2R book (2021) and 13.50% vs 12.04% (2014). The reproduction kept the same ordering (2021 D2 9.67 vs C/M 8.04; 2014 D2 13.14 vs M 9.27). Win rate on the trail is about 35–39%. That is expected. v0 live stays on the 2R target (`stops.reward_r = 2.0`) until a later gate passes.

**Watch:** the trail's deeper drawdown. Appendix 2014 D2 max drawdown was −38.61% vs −27.54% for the 2R book. Judge the exit on CAGR, Sharpe, and max drawdown together, and on whether satellite drawdown stays inside the benchmark's (success metric S4). Do not switch to 2R because the win rate looks low, and do not narrow 3.0 to chase the 2014 Sharpe gap.

**Sources:** [Chandelier definition, k = 3](https://www.luxalgo.com/library/concept/trailing-method-taxonomy/), [Le Beau 22-day, 3×ATR](https://karenwong.substack.com/p/chandelier-exit), [ATR trail multiples 2.5–3.5, default 3](https://www.incrediblecharts.com/indicators/atr_average_true_range_trailing_stops.php), [TrendSpider ATR trail](https://trendspider.com/learning-center/atr-trailing-stops-a-guide-to-better-risk-management/).

## Q3. Regime gate

**Default:** hard gate. `regime.gate = true`, `regime.symbol = "SPY"`, `regime.sma = 200`. No new entries while SPY's close is at or below that average. Open positions keep their stops and trail. Half-size is not a default.

**Confidence:** medium.

**Why:** Faber's 10-month average (the monthly form of the 200-day average) is a binary in-or-cash rule. On the original sample it cut drawdown sharply and was stable across roughly 3- to 12-month windows. Daniel and Moskowitz show momentum crashes in rebounds after bears, mostly from the short leg; a long-only book lags rather than crashes, so the gate is a drawdown tool. Appendix A is mixed on CAGR: 2021 D2 (gate on) 11.93% and max drawdown −26.88% vs K (gate off) 9.44% and −34.25%; 2014 K's CAGR was higher (16.78% vs 13.50%). The reproduction did not repeat the 2021 ordering (K 15.51 vs D2 9.67) and that K figure is outside the ±2 point band, so it cannot justify turning the gate off. Half-size was not a pre-registered variant and would add a free parameter.

SPY is the timing series already in Section 6.4. It is not added to `universe.txt` and it is not a recommended holding. Whether the user wants an unscreened index as a timer is his call.

**Watch:** months spent in cash inside the satellite while the core (Q1) stays invested. A string of missed rebounds is the cost already visible in the 2014 window. Review that cost. Do not disable the gate after one rally.

**Sources:** [Faber, SSRN](https://mebfaber.com/wp-content/uploads/2016/05/SSRN-id962461.pdf), [Faber parameter stability](https://mebfaber.com/timing-model/), [CXO summary of the drawdown cut](https://www.cxoadvisory.com/technical-trading/long-term-outperformance-from-trends-defined-by-moving-averages/), [Daniel and Moskowitz 2016](https://www.kentdaniel.net/papers/published/jfe_16.pdf).

## Q4. Liquidity floor

**Default:** `liquidity.min_price = 5` and `liquidity.min_median_dollar_volume = 10000000`, using the trailing 20-session median of close × volume, recomputed each session.

**Confidence:** high.

**Why:** Jegadeesh and Titman dropped stocks below $5 at portfolio formation. FINRA treats stocks under $5 as the usual penny-stock price band: wider spreads, thinner books, easier to move. A $10M median dollar-volume floor keeps a 20% slot small relative to trading activity. At $100,000 sleeve equity the slot is $20,000, which is 0.2% of a $10M day. At $500,000 sleeve equity it is 1% of that day. The floor is point-in-time (trailing 20 sessions), which is the form that avoids a full-sample average pulling in names that became liquid later.

Names on the screened list that fail the floor are skipped with a plain reason. That is the right default for this turnover. A user who has accepted smaller screened names can lower `liquidity.min_median_dollar_volume` in config later. The built-in default stays $10M. There is no separate "halal small-cap" exception in this note.

**Watch:** how many universe names the floor rejects. If most of the screened list fails, the list and the floor disagree and the user should see that count before changing the floor. Also watch realized slippage against the planned entry (success metric C4: median absolute gap at most 0.1R).

**Sources:** [Jegadeesh and Titman 1993, price filter](https://www.albany.edu/sites/default/files/2019-08/Anurag_Banerjee.pdf) (the paper's $5 exclusion, as restated with the method), [FINRA on stocks under $5](https://www.finra.org/investors/insights/low-priced-stocks-big-problems), [17 CFR § 240.3a51-1](https://www.law.cornell.edu/cfr/text/17/240.3a51-1) (the $5 price element of the penny-stock definition; listed NMS stocks have other exceptions), [point-in-time ADV](https://quantmemo.com/concepts/liquidity-screens-and-tradability-filters), [Investopedia ADTV and trade size](https://www.investopedia.com/terms/a/averagedailytradingvolume.asp).

## Q5. Slots

**Default:** `portfolio.slots = 5`, `portfolio.max_position_frac = 0.20`. Five times 20% is 100% of the sleeve, which fits a cash account. v0's `max_concurrent_positions = 4` stays the live checklist value.

**Confidence:** high relative to the four-at-25% alternative.

**Why:** Appendix I (5 × 20%) beat D2 (4 × 25%) on CAGR in both windows: 13.90% vs 11.93% (2021) and 17.88% vs 13.50% (2014). The reproduction kept I ahead of D2 (13.68 vs 9.67 in 2021; 14.34 vs 13.14 in 2014). v0's median notional was 31.8% of equity, so four slots do not fit in cash. The 20% cap is also the tighter single-name gap bound. A 25% cap still left a worst trade of −4.97% of equity before the earnings exit (Appendix A.2).

**Watch:** correlation. Five stocks in one industry are one bet. The redesign drops the sector-heat config; the user still has to avoid a one-industry universe. Do not move to eight or ten slots without a new pre-registered run.

**Sources:** Appendix A variants I and D2, and the reproduction tables. Position-count practice for a concentrated book is secondary to those measured variants.

## Q6. Entry order

**Default:** `entry.cap_atr = 1.0`. The live ticket is a limit at the signal close plus 1×ATR(14), or marketable only up to that price. Size still uses the signal close and the initial stop (`close − 1.5×ATR`). v0 has no entry cap and does not gain one in this decision.

**Confidence:** medium.

**Why:** The tested v1 book includes this cap (`VARIANTS["v1"]`). A tight 0.25×ATR chase cap cost about 4–6 CAGR points in Appendix H, so the tight cap is rejected. One times ATR is the pre-registered catastrophe cap: it limits how far a gap-up can push the fill above the close that was used for the 1% risk math. If the fill is above the signal close and the stop stays at `close − 1.5×ATR`, dollar risk per share is larger than planned. The cap bounds that.

The reproduction also shows the cap binds. On the 2021 window, variant I and I with market-on-open were the same book (CAGR 13.68, Sharpe 0.93) because I's `entry_cap_atr` is unset. I with a 1×ATR cap was CAGR 11.68 and Sharpe 0.83. Section 6.4 hoped the cap would almost never bind. On that I book it bound enough to matter. That is a reason to watch the bind rate. It is not a reason to drop the cap from the already-tested v1 variant, and it is not a reason to edit the variant so the 2014 gate passes.

**Watch:** in `review`, the share of plans whose next open is above `entry_cap`, and the later R of those skipped names. If the skipped names are where the profit was, the next pre-registered comparison is market-on-open versus the 1×ATR cap. IBKR Market-on-Open (OPG) joins the opening auction and must be in before the exchange cutoff (Nasdaq generally 09:28 ET). IBKR Lite's commission-free treatment of OnOpen and OnClose orders ends when those orders exceed 10% of monthly US stock volume; see Q12. This note does not assume Lite.

**Sources:** reproduction rows "I market-on-open" and "I with 1×ATR cap"; [IBKR order types, Market-on-Open](https://www.ibkrguides.com/traderworkstation/order-types.htm); [Nasdaq LOO/MOO cutoff](https://www.interactivebrokers.com/en/trading/ordertypes.php).

## Q7. Risk for the first 20 real trades

**Default:** built-in `risk.per_trade` stays **0.01**, including every backtest variant that already uses 1%. The operator sets `risk.per_trade = 0.005` in `~/.swing/config.toml` until **20 closed real fills** are in `book.jsonl`, then sets it back to `0.01`. Plans are not fills. The 20-trade count is a process check (ticket followed, stop placed, earnings exit placed). It is not proof of an edge. Proof stays at success metric P2: mean trade R minus 2 standard errors above 0 after at least 100 closed trades, and the sleeve ahead of the benchmark over at least 12 months.

**Confidence:** high on leaving the code default at 1%; medium on 20 as the probation length.

**Why:** Appendix G at 2% risk had a lower CAGR (7.20% vs 7.71%) and a deeper drawdown (−37.10% vs −28.73%) than the 1% book. Van Tharp's published sizing rule is about 1% of equity to the stop, so one trade cannot dominate. Systems with a short live sample are sized smaller until the R-multiple record exists. Van Tharp's System Quality Number is considered preliminary near 30 trades and is meant to be read after 100 or more. Twenty trades cannot estimate expectancy: Appendix A.1's per-trade standard error is about 0.018 on thousands of trades, so 20 live trades will have a much wider error. Changing the built-in default to 0.005 would resize the live v0 checklist and would make new backtests incomparable with the gate tables.

**Watch:** the operator has to edit the toml by hand after the 20th close. `review` can print the closed-trade count. Do not add an automatic ratchet inside the backtest.

**Sources:** [AmiBroker note on the 1% Van Tharp risk model](https://www.amibroker.com/kb/2014/10/12/position-sizing-based-on-risk/), [1% rule write-up](https://medium.com/@nicholasvardy/van-tharp-and-the-power-of-position-sizing-44597158863), [SQN sample size, 30 preliminary and 100+ for a live system](https://journalplus.co/metrics/system-quality-number), [size small until about 100 trades](https://tradingmomentum.substack.com/p/the-art-and-science-of-position-sizing).

## Q8. Earnings

**Default:** for `EQUITY`, never hold through a report. `earnings.strict = true`. Forced exit is a market-on-close on the session before the report **calendar date**, ignoring time of day. `earnings.min_room_sessions = 3`. No entry on the session after a report (`earnings.after_days = 1`). `ETF` skips the gate and the card says so. Unknown instrument type is treated as `EQUITY`.

v0's live rule stays the entry blackout (`blackout_before_days = 2`, `blackout_after_days = 1`). The forced exit is v1 behavior and is not switched on by this file.

**Confidence:** high.

**Why:** A stop does not contain an earnings gap. Appendix A: after the v0 entry blackout, 12.9% of 2021+ trades still held through a report, and the worst was −6.51R. Exiting before the report beat holding through it (C 7.71% CAGR vs E 5.78% in Appendix A; the reproduction kept C ahead of E, 8.04 vs 2.91). Investopedia's gap-risk note is the same operating rule: close the position before the report, on the prior close. Using the calendar date, and exiting the session before that date, is safe for both before-the-open and after-the-close reports. A wrong "after close" label on a before-the-open report is a full gap. Giving up one session on a true after-close report is the accepted cost. Finnhub's free calendar is about one month forward, so the date can be unknown outside that window; unknown date on a single stock remains no-trade under `earnings.strict`.

**Watch:** disagreement between Finnhub and yfinance (`WARN_EARNINGS_DISAGREE` in the plan: earliest date wins). Confirmed report dates that move. ETFs mis-tagged as equities, which would block them. This is a risk rule for single-stock gaps, not a screen of the business.

**Sources:** [Investopedia, gap risk, exit before the report](https://www.investopedia.com/terms/g/gaprisk.asp), [Finnhub earnings calendar, free tier is one month](https://finnhub.io/docs/api/earnings-calendar), Appendix A variants C and E, Appendix A.1 earnings hold-through figures.

## Q9. Survivorship-free research data

**Default:** buy one paid US end-of-day set that includes delisted names, and use it only as a harness adapter. Do not put that key on the live scan path. Do not block daily use of the CLI on the purchase. First choice: **Sharadar Prices, full history** (the equity-price table Nasdaq Data Link still aliases as SEP), which is a REST download and runs on macOS. On 2026-10-02 the Sharadar subscribe page listed that plan at $39 per month or $299 per year. Second choice: **EODHD EOD Historical** if the only need is delisted OHLCV and delisted symbols are included on the plan being bought; that plan was listed at $19.99 per month, with a 30+ year end-of-day claim, and EODHD's own delisted note says names removed before 2018 have end-of-day history only. Skip Norgate for this workflow: the database lives on Windows (or a Windows VM) and access ends when the subscription ends.

After the data arrives, rerun the pre-registered variants and the v1 gate. Publish the tables. Do not search parameters on the new file.

**Confidence:** high on buying a delisted set before trusting the momentum gap; medium on Sharadar over EODHD.

**Why:** Appendix A says the 50-name survivor list inflates momentum ranking most. The 2014 failure is "v1 Sharpe 0.90 vs random 0.95" on that list. A survivor-biased win would not have been enough to ship, and a survivor-biased loss is not something to tune away. Massive Basic cannot fill this role: it is end-of-day, 2 years of history, and 5 calls per minute. The long gate window needs history from 2013 and names that no longer exist. Sharadar's own description is active and delisted US coverage, point-in-time, back to the 1990s. That matches a macOS harness. Norgate's survivorship handling is well regarded and the wrong operating system for this CLI.

**Watch:** license is personal-use; prices on those pages move; confirm the file actually contains delisted common stocks and split-adjusted OHLCV before building the adapter. Adjusted-price conventions must match the harness (the reproduction uses yfinance auto-adjusted bars). A mismatch there will look like an edge change.

**Sources:** [Sharadar](https://sharadar.com/), [Sharadar subscribe prices as of this research pass](https://sharadar.com/subscribe), [Nasdaq Data Link, Sharadar equity prices from 1998, active and delisted](https://data.nasdaq.com/publishers/SHARADAR), [EODHD pricing](https://eodhd.com/pricing), [EODHD delisted coverage](https://eodhd.com/financial-apis/delisted-stock-companies-data-2), [Norgate data access is a Windows database](https://norgatedata.com/), [Norgate listed as Windows-only in a vendor comparison](https://quantpedia.com/best-historical-market-data-providers/).

## Q10. v0 journal

**Default:** every `journal.jsonl` line is a plan. Archive the file as `journal.v0.jsonl` and import `ENTER_LONG` lines into `plans.jsonl` only. Import nothing into `book.jsonl`. `src/swing/book.py` `import_v0_journal` already does this and leaves the original journal in place. If a specific line was a real IBKR fill, the user records that fill with the manual buy command after he confirms the shares, price, and date. A bulk import into the book is not the default.

**Confidence:** high.

**Why:** This research pass did not read a private journal and cannot know which lines were fills. Plans that are treated as fills double-count risk and brick the slot count. The redesign's separation of `book.jsonl` (fills) and `plans.jsonl` (intent) is the accounting rule. Forward-scoring those archived plans is still useful.

**Watch:** a later "import my old fills" request needs an explicit per-line confirmation of ticker, shares, price, and date. A line with `decision = ENTER_LONG` and a planned entry is not that confirmation.

**Sources:** `src/swing/book.py` `import_v0_journal`; redesign plan Section 6.5.

## Q11. IBKR account type

**Default:** the brokerage account used for this book is a **cash** account. `account.mode = "cash"` is already the only accepted config value. The CLI sizes off settled cash either way. A margin account can still borrow if a manual ticket is wrong, and the CLI never sees that ticket.

**Confidence:** high.

**Why:** Regulation T's cash-account rule requires full cash payment and pulls the delay-payment privilege for 90 days if a security is sold before it has been paid for (12 CFR § 220.8). US stocks have settled T+1 since 2024-05-28, so a sale's cash is not available for a new purchase that will itself be sold the same day. The harness already withholds unsettled same-day sale proceeds. A cash account makes a typo fail at the broker instead of opening a margin loan. This product does not place orders, so the account type is an operator fact the software cannot enforce.

**Watch:** settled cash versus buying power in the IBKR window. Buying power can include unsettled proceeds. Size from settled cash. Good-faith and free-riding restrictions are broker-side; `swing doctor` can only remind the user.

**Sources:** [12 CFR § 220.8](https://www.law.cornell.edu/cfr/text/12/220.8), [IBKR on T+1](https://www.interactivebrokers.com/campus/traders-insight/securities/stocks/t1-settlement-what-it-means-for-traders-and-investors/).

## Q12. Account size and commissions

**Default:** no assumed equity. `account.equity_usd` stays unset in code until the operator sets the satellite sleeve (Q1). Pricing choice for this book's order size: **IBKR Pro Tiered**. Re-read the schedule in the account portal before relying on it.

Published US stock schedule used here (IBKR commissions page, retrieved 2026-10-02):

| Plan | Rate | Minimum per order | Maximum per order |
|---|---|---|---|
| Pro Fixed | $0.005 / share | $1.00 | 1% of trade value |
| Pro Tiered | $0.0035 / share at the lowest volume tier | $0.35 | 1% of trade value, plus exchange, clearing, and regulatory fees |
| Lite | commission-free US listed stocks for US residents | see the 10% auction note below | US residents only |

Illustrative Fixed drag at the plan's 60–80 round trips a year, counting two orders per round trip (entry and exit) at the $1 minimum: $120–$160 a year. That is 1.2–1.6% of a $10,000 account and about 0.5% of a $25,000–$30,000 account. Seventy round trips at $2 is $140, which is 0.5% of $28,000. v1's tested turnover is in that same band (77 trades/year in 2021, 60 in 2014).

Tiered's $0.35 minimum is the better published fit for the small share counts this sleeve will send. It is not $0.35 all-in: exchange, clearing, and regulatory fees are extra. IBKR Lite is available to US residents; this CLI's user timezone is Africa/Cairo, so Lite may be unavailable, and Lite's commission-free treatment of OnOpen, OnClose, outside-regular-hours, and sub-$1 orders stops when those orders exceed 10% of monthly US stock volume. This book uses an opening entry and a closing earnings exit, so do not plan on Lite staying free.

**Confidence:** high on leaving equity unset and on Fixed's $1 minimum being material under about $25,000; medium on Tiered after add-on fees.

**Watch:** the first activity statement. If most orders are OnOpen or OnClose, confirm the tier actually charged. A 20% satellite on a $10,000 total account is a $2,000 sleeve; $140 of minimums would be 7% of that sleeve. At that size, pay Tiered and keep the sleeve small in weight only if the dollar sleeve can still carry the commissions. Do not cut slots or risk inside the backtest to make the commission line look smaller.

**Sources:** [IBKR US stock commissions](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php), [IBKR Fixed vs Tiered overview](https://www.interactivebrokers.com/en/pricing/commissions-home.php), [The Poor Swiss, 2026, Tiered cheaper on small US orders](https://thepoorswiss.com/ib-fixed-or-tiered-pricing/).

## Q13. Universe size and ETFs

**Default:** `universe.txt` should hold **at least 20** user-screened USD stocks, with a working target of **30–50**. Include an ETF only when the user has already put that ETF on the screened list, and tag it `ETF` so the earnings gate skips it (Q8). The core ETF from Q1 stays out of `universe.txt` so the CLI does not swing the core. SPY stays out of `universe.txt`.

Below 20 names, `scan` may still run. `review` should label the rank as a thin universe. Do not add a hard block in the live checklist.

**Confidence:** medium.

**Why:** The published momentum result is a sort of a broad cross-section into deciles (Jegadeesh and Titman; the usual formation window is 3–12 months with a skip, which is why Section 6.4 uses 126 sessions and a 5-session skip). A personal book that buys the top one to five names needs enough names for the order to mean something. At 20 names the top slot is the top 5%, which is coarse and usable. Under about 10 names the rank is almost the same as taking every name that triggered. The smoke universe was 50 current large caps. That is the target shape, built from the user's list, not from that survivor list.

**Watch:** a list of 50 names that the $10M floor cuts to 8 is a 8-name universe. Count names that pass liquidity, not lines in the file. ETFs inside the tradable list must be tagged or they will fail the equity earnings rule.

**Sources:** [Jegadeesh and Titman 1993](https://www.bauer.uh.edu/rsusmel/phd/jegadeesh-titman93.pdf), [formation window and one-month skip](https://link.springer.com/article/10.1007/s11408-022-00417-8), [12-1 implementation note](https://www.pfolio.io/academy/cross-sectional-momentum).

## Q14. Keys

**Default:** the operator gets the free **Massive** key and the free **Finnhub** key. Context.dev stays out. Both keys are already named in `.env.example`. Live bars stay on yfinance until the operator sets `SWING_BARS_PROVIDER=massive` (or `data.bars_provider = "massive"`). Do not flip that built-in default in this decision. When Massive is selected, the fallback remains yfinance, then `DATA_STALE`. A missing Massive key is a doctor warning plus that fallback, not a reason to block a fresh yfinance bar.

Massive Basic, as listed on the pricing page: $0, 5 API calls per minute, 2 years of history, end-of-day US stocks, corporate actions. The grouped-daily endpoint is the one-call update for the whole universe. Two years is enough for a daily scan (the v1 minimum is 260 sessions) and not enough for the 2014 harness window (Q9).

Finnhub free: 60 calls per minute, earnings calendar limited to about one month of history plus new updates. Use it for `/calendar/earnings` only. Dividend and candle endpoints are premium and stay unused.

Context.dev affected no checklist math and is already documented as not a dependency (ADR 0001, `docs/architecture.md`). It does not return as a required key.

**Confidence:** high.

**Why:** Two free keys cover official end-of-day bars and a real earnings calendar. yfinance remains the no-key fallback because it is unofficial and rate-limits. Requiring the keys in the sense of "doctor tells you to get them" matches the product. Requiring them in the sense of "no key, no trade, even when Yahoo is fresh" would create the outage class the Finnhub dividend 403 already caused.

**Watch:** Massive's 5 calls per minute. A cold per-ticker backfill has to stay throttled; the steady-state update is one grouped-daily call per missing session. Finnhub's one-month earnings window means a report more than about 35 days out can be unknown: strict mode then skips the stock, which is the capital-protection behavior. Benzinga earnings on Massive is a paid add-on and is not part of this default.

**Sources:** [Massive pricing](https://massive.com/pricing), [Massive rate limit](https://massive.com/knowledge-base/article/what-is-the-request-limit-for-massives-restful-apis), [Massive grouped daily](https://massive.com/knowledge-base/article/how-can-i-get-the-daily-prices-for-all-stocks-using-massives-market-data), [Finnhub pricing, 60 calls/minute](https://finnhub.io/pricing), [Finnhub earnings calendar free tier](https://finnhub.io/docs/api/earnings-calendar).

## Q15. Home folder

**Default:** `~/.swing`. This is already `swing_home()` in `src/swing/home.py`. Keep it. The macOS v0 folder `~/Library/Application Support/swing` is copied once when `~/.swing` is absent, and the source is left in place. `SWING_HOME` overrides the default. `.env` in that directory should be mode `0600`.

**Confidence:** high.

**Why:** Command-line tools on macOS are expected to keep user files in a home dot directory or under the XDG paths (`~/.config`, `~/.local/share`), including by tools that ship with the system such as git. `~/Library/Application Support` is the GUI-app location, it contains spaces, and it is easy to lose across a re-clone. A full XDG split would separate config, data, and cache. This CLI wants one directory the operator can find: `config.toml`, `.env`, `universe.txt`, `book.jsonl`, `plans.jsonl`, and `cache/`. `~/.swing` is that single root. The path is the same on Linux and macOS, which matches how the tests inject `home`.

**Watch:** a machine that already has both directories. Migration copies only when the destination is absent, so a later file edited only in Application Support will not flow across. `doctor` can say which directory it is using.

**Sources:** [XDG base directory defaults](https://xdgbasedirectoryspecification.com/), [CLI tools on macOS and Application Support](https://becca.ooo/blog/macos-dotfiles/), [Atmos moving a CLI off Application Support onto the XDG paths](https://atmos.tools/changelog/macos-xdg-cli-conventions).

## Config values to keep straight

Live v0 built-ins, unchanged:

| Key | Value |
|---|---|
| `account.mode` | `"cash"` |
| `account.equity_usd` | unset |
| `risk.per_trade` | `0.01` |
| `max_concurrent_positions` | `4` |
| `stops.atr_period` | `14` |
| `stops.atr_multiple` | `1.5` |
| `stops.reward_r` | `2.0` |
| `earnings.strict` | `true` |
| `earnings.blackout_before_days` | `2` |
| `earnings.blackout_after_days` | `1` |
| `data.bars_provider` | `"yfinance"` |
| `timezone.user` | `"Africa/Cairo"` |
| `shariah.screen_in_v0` | `false` |
| `shariah.provider` | `null` |

Operator `~/.swing/config.toml`, not a code default:

| Key | Value |
|---|---|
| `account.equity_usd` | the satellite sleeve only; start near 20% of total USD equity |
| `risk.per_trade` | `0.005` for the first 20 closed real fills, then `0.01` |
| `benchmark.symbol` | `"SPUS"`, or the screened core ETF actually held |

v1 surface, already the backtest variant, not the live checklist:

| Key | Value |
|---|---|
| `portfolio.slots` | `5` |
| `portfolio.max_position_frac` | `0.20` |
| `regime.gate` | `true` |
| `regime.symbol` | `"SPY"` |
| `regime.sma` | `200` |
| `trend.sma` | `200` |
| `rank.lookback` | `126` |
| `rank.skip` | `5` |
| `exit.mode` | `"trail"` |
| `exit.trail_atr` | `3.0` |
| `exit.target_r` | `2.0` (selectable) |
| `entry.cap_atr` | `1.0` |
| `stops.atr_period` | `14` |
| `stops.initial_atr` | `1.5` |
| `earnings.strict` | `true` |
| `earnings.min_room_sessions` | `3` |
| `earnings.after_days` | `1` |
| `liquidity.min_price` | `5` |
| `liquidity.min_median_dollar_volume` | `10000000` |
| `benchmark.symbol` | `"SPUS"` |

Not financial advice. Not a Shariah certification.
