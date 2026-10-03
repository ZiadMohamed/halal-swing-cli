# Peer systems

Date: 2026-10-03
Status: research note. No live change. No bake-off opened.
Reads: `src/swing/brain/checklist.py`, `src/swing/brain/setups.py`, `src/swing/config.py`, `src/swing/backtest.py`, `config/v1-surface.example.toml`, `docs/decisions/SECTION8_ANSWERS.md`, `docs/backtests/v1-gate.md`, `docs/REDESIGN_PLAN.md`, `docs/architecture.md`, `docs/adr/0002-redesign.md`

This note checks three proposed upgrades against the published methods and against the book that already exists. It does not retune a backtest, does not change `ChecklistBrain`, and does not make a Shariah ruling. The universe file remains the user's screen.

Not a certified edge. Not financial advice. Not a Shariah certification. Not a fatwa. Not a broker fill.

## Calls

| Upgrade | Call | Frozen rule kept on file |
|---|---|---|
| 1. Faber 10-month or Antonacci 12-month gate on new ENTERs | **Skip** | The only trend gate already written down is Q3: SPY daily close above SMA(200), hard, new entries only. It stays unshipped. |
| 2. 12-1 relative strength, setups only in the top half of the user's list | **Skip** | The recorded rank stays `lookback = 126`, `skip = 5`, and it stays inside the unshipped v1 book. No top-half and no quartile filter is added. |
| 3. Down-only SPY volatility throttle that halves risk | **Skip** | `risk.per_trade` stays 0.01 in code. The operator half-size in Q7 is a count of closed fills, not a volatility switch. |

Nothing here is worth a new pre-registered bake-off. The live path stays the v0 checklist: mutex `BO_RVOL` then `PB_EMA` then `RSI2_MR`, stop at entry minus 1.5×ATR(14), target at 2R, four positions, earnings blackout, `risk.per_trade = 0.01`. In `ChecklistBrain`, the regime gate is set to pass with no test. RSI(2) is the only live setup with its own SMA(200), and that average is on the stock, not on SPY. Breakout uses SMA(50). Pullback uses EMA(50) and EMA(20).

v1 already bundled a SPY SMA(200) regime gate, a per-ticker SMA(200) trend filter, and a momentum rank. `docs/backtests/v1-gate.md` (no parameter changed after the run):

| Window | Book | CAGR % | Sharpe |
|---|---|---:|---:|
| 2021-01-04 → 2026-09-30 | v0 | −9.93 | −0.73 |
| 2021-01-04 → 2026-09-30 | v1 | 13.67 | 0.96 |
| 2021-01-04 → 2026-09-30 | v1 random rank | 4.96 | 0.50 |
| 2014-06-02 → 2026-09-30 | v0 | 5.86 | 0.50 |
| 2014-06-02 → 2026-09-30 | v1 | 12.74 | 0.90 |
| 2014-06-02 → 2026-09-30 | v1 random rank | 10.55 | 0.95 |

v1 beat v0 on CAGR and Sharpe in both windows. In the 2014 window the random-rank Sharpe is higher (0.95 vs 0.90). That failed the ship rule. Section 8 leaves the live checklist on v0 and says the rank window, the regime gate, and the other v1 knobs stay where they are. A nearby rule run on the same survivor list would be a search for a pass. Q9 still says: when a delisted history file exists, rerun the variants already pre-registered. Do not add these three to that list.

## How this pass was checked

Primary pages and papers were read on 2026-10-03. Context.dev web-answers ultra was not used. A last search for a Zarattini RSI reprint stopped on a Context credit limit (`401 USAGE_EXCEEDED`, one credit left). The Connors decay figure already printed in `docs/REDESIGN_PLAN.md` Section 2.3 was not re-opened, so it is not repeated here as a new measurement. The SSRN PDF for Antonacci abstract 2042750 did not load (the site returned a block page). His rule is taken from his own later description, cited below, and from the search snippet of that PDF.

## 1. Trend gate — skip

**Call:** skip. Do not open a bake-off of a 10-month SMA, a 12-month absolute-momentum sign, or an "either one blocks the entry" combination.

**What is already frozen.** Q3 is a hard gate. `regime.gate = true`, `regime.symbol = "SPY"`, `regime.sma = 200`. No new entries while SPY's close is at or below that average. Open positions keep their stops and trail. Half-size is not a default. Those keys live in `config/v1-surface.example.toml` and in `VARIANTS["v1"]`. `swing analyze` does not load them. The same gate sat inside the v1 book that lost the 2014 Sharpe comparison.

**Faber, read from the updated paper.** Meb Faber, "A Quantitative Approach to Tactical Asset Allocation," the PDF at `mebfaber.com` dated from the SSRN id 962461 file. Rule, in the paper's words: buy when the monthly price is above the 10-month simple moving average; sell and move to cash when the monthly price is below it. The paper then says the risk drop comes from moving to T-bills. On the 1901–2012 S&P path in that PDF, average returns are 11.26% (buy and hold) and 11.22% (timing); compounded returns are 9.32% and 10.18%. The late-1920s drawdown in Figure 8b falls from 83.66% to 42.24%. Timing underperforms the index in about half of years. A 3-month through 12-month average "seem to work similarly"; the 10-month length is not a unique solution. The GTAA book in the same paper is five sleeves — US stocks, foreign stocks, bonds, real estate, and commodities — and the 1973–2012 timing drawdown cited there falls from 46% to less than 10%.

The redesign plan's older line (drawdown from 83.7% to 50.0% over 1900–2005) is an earlier cut of this literature. The PDF read on this pass is the 1901–2012 update above. Both cuts are index timing, with T-bills as the alternative.

**Antonacci, from the pages that loaded.** Relative momentum compares one asset with another. Absolute momentum compares an asset with its own trailing record; he also calls that time-series momentum. On the 2017 Faber podcast he describes the implemented equity switch as: hold the S&P 500 when it has been positive relative to Treasury bills over the past 12 months, and otherwise hold aggregate bonds. He says that version earned about 210 basis points a year over the S&P on the history he was describing, against about 270 for relative momentum alone. Those are his spoken figures, not a table recomputed here. His FAQ (page modified 2026-03-24) says GEM has been in bonds less than 30% of the time, that bonds account for about 20% of GEM's profits, and that government bonds or Treasury bills can replace aggregate bonds with a modestly lower expected return. The SSRN listing for "Risk Premia Harvesting Through Dual Momentum" (abstract 2042750) describes absolute momentum as a positive excess return over Treasury bills for the past year. The PDF itself did not load on this pass.

**Why this is not a new test.**

- One trend gate is already on file. Faber's 10-month average is the monthly form of the 200-day average, which is the sentence Q3 already uses. His own stability check says the 3- to 12-month window is not a separate discovery. Adding the 10-month SMA beside SMA(200) is a second look at the same idea.
- Antonacci's hurdle is a Treasury-bill excess return, and the holding he switches into is aggregate bonds (or T-bills, in the FAQ substitute). This book is cash-long USD equity. Uninvested satellite cash earns no interest. The published gap over the S&P includes that interest-bearing sleeve. A zero-yield cash version is a different strategy, and it was not the one in his numbers.
- "Block if Faber fails or Antonacci fails" requires both tests to pass. That is two gates. Q3 rejected an extra half-size parameter for the same reason: it was not pre-registered.
- Appendix A already turned the SMA(200) gate off inside the momentum-and-trail book (variant K versus D2). CAGR was mixed across windows. The reproduction missed the 2021 no-gate CAGR by more than 2 points (15.51 versus the appendix's 9.44). That sample cannot support a finer trend definition.
- The published object is "own the index, or own the safe asset." It is not a filter on a three-setup swing ticket with a 1.5×ATR stop and a 2R target.

**The rule that stays frozen, and is not re-run from this note.** SPY close above its 200-session simple average, judged at the signal close. Fail means no new ENTER. Open positions are unchanged. No 10-month SMA is computed beside it. No 12-month excess return over bills is computed beside it. SPY stays out of `universe.txt`. Whether an unscreened index may time the satellite remains the user's call, as Q3 already says.

## 2. Relative strength — skip

**Call:** skip. Do not open a bake-off of a 12-1 filter, a top-half cutoff, or a top-quartile cutoff.

**What is already frozen.** Section 6.4 and the v1 surface rank candidates by `close[t−5] / close[t−126] − 1`. That is about six months, skipping about one week. It is a sort among names that already triggered, used to fill slots. It is the rank inside the book that lost the 2014 Sharpe test to a random sort of the same triggers (seed 42). Section 8 names the rank window as something not to retune, and it names cross-sectional momentum as the effect a survivor list inflates most. The harness universe is today's large caps. Earnings are off before 2020.

**Jegadeesh and Titman 1993, read from the Journal of Finance PDF.** NYSE and AMEX, 1965–1989. At each month the stocks are sorted on the past J months into ten equal-weighted deciles. The strategy buys the winner decile and sells the loser decile, held for K months, with overlapping cohorts. J and K are one to four quarters. A second set of 16 strategies skips a week, to step past the one-week and one-month reversals they cite from Jegadeesh (1990) and Lehmann (1990). The 12-month formation and 3-month hold earns 1.31% a month with no lag and 1.49% a month with a one-week lag, as a zero-cost long-short spread. The 6-month formation is about 1% a month. The 6-month/6-month strategy they discuss in detail compounds to 12.01% a year excess. The highlights of that PDF did not contain a five-dollar price screen.

The one-month skip is a later convention. Ken French's momentum factor, read from the data-library page on this pass, uses prior return from month t−12 through t−2. Winners and losers are split at the 30th and 70th percentiles of NYSE prior return, then intersected with a median size split. The factor is long the high prior-return side and short the low side. That is a top-30% tail of a broad cross-section, not the top half of a personal list.

**The five-dollar screen is the 2001 follow-up.** Jegadeesh and Titman's 1999 NBER draft (working paper 7159, later the 2001 Journal of Finance paper) says they exclude stocks priced below $5 at the start of the holding period, and that this exclusion is why variability is smaller than in the 1993 series. Q4's sentence attributes that screen to the 1993 paper by way of a later restatement. The floor in Q4 stays. The citation is tightened in the conflict list below. It does not create a relative-strength test.

**Why a top-half filter on this list is a different experiment from the papers, and still the wrong next run.**

- The published spread is winners minus losers. The short leg is forbidden here. Daniel and Moskowitz (2016) put the crash on that short leg: after a decline the loser decile is high-beta, the rebound hurts the short, and the long-only book lags rather than crashes. Keeping only the long leg drops the published spread and keeps the part Section 8 already called a drawdown lag.
- A decile of NYSE/AMEX, or French's 70th percentile, needs a broad cross-section. Q13 sets the working list at 30–50 user-screened names, and says that under about 10 names the rank is almost "take every trigger." The top half of 30 names is 15 names. The top quartile is 7 or 8, which falls through the floor Q13 treats as a thin universe. Neither cutoff is the paper's cutoff. Choosing between them after a result would be a search. Choosing either of them before a result still would not be Jegadeesh-Titman.
- RSI(2) is a pullback inside an uptrend. A relative-strength gate in front of all three setups would require that pullback to also be a cross-sectional winner. That changes the third setup. The third setup stays as it is.
- v1's 126/5 rank is already the six-month cousin of this idea, with a one-week skip close to the 1993 week skip. It failed the random-rank Sharpe test on the sample that inflates it. A 12-1 top-half rule is a new window and a new cutoff on that same lever. Section 8 says a 0.05 Sharpe gap is not a reason to search parameters until the gap flips.

**The specification that is written down so it is not reinvented, and is not run.** There is no new relative-strength rule. The unshipped rank remains 126 sessions, skip 5, sorting candidates that already passed the v1 gates. It is not wired to `swing analyze`. A top-half or top-quartile label on `universe.txt` is not added.

## 3. Volatility throttle — skip

**Call:** skip. Do not open a bake-off of a down-only SPY volatility cut. Do not scale risk up.

**What the papers actually scale.** Cederburg, O'Doherty, Wang, and Yan (Journal of Financial Economics, 2020), read from the working PDF: a volatility-managed return is `c* / σ²(t−1) × f(t)`, where `σ²` is the previous month's realized variance of daily excess returns and `c*` is a constant chosen so the managed and unmanaged series have the same full-sample variance. That constant is not known in real time. Across 103 equity strategies, direct Sharpe comparisons do not systematically favor the managed book (53 higher, 50 lower, few significant). Spanning-regression alphas in the style of Moreira and Muir (2017) show up, and the trades those regressions imply are not implementable in real time. Reasonable out-of-sample versions generally have lower certainty-equivalent returns and lower Sharpe ratios than the unmanaged portfolios. The position `c* / σ²` is leverage. In their Table 1 discussion the median position is near one, and the 99th percentile of required leverage exceeds 400% and reaches 864% on the momentum strategy.

The same paper says the momentum strategies are the pocket where volatility management does improve Sharpe, in line with Barroso and Santa-Clara (2015) and Daniel and Moskowitz (2016). Those strategies are the long-short factor. Daniel and Moskowitz locate the crash in panic states: the market has already fallen, volatility is high, and the rebound arrives while the short leg is short the high-beta losers. A cash-long book does not hold that short leg. Q3 already used that paper as the reason a regime gate is drawdown control.

A rule that only cuts risk in half, and never raises it, is not the Moreira-Muir strategy. It drops the levered-up months, which are the months their scaler is above one, and it keeps a binary threshold their formula does not use. Cederburg's point on the market portfolio is that high volatility is a poor real-time signal for getting out, because the implementable version does not beat simply holding the unmanaged portfolio. Using SPY's volatility to resize a single-name swing ticket is a further step away from the factor they scaled.

**Why it collides with the operator file.** Q7 leaves the built-in risk at 0.01. The operator may set `risk.per_trade = 0.005` until 20 closed real fills, then set it back. That count is a process check. Section 8 says not to add an automatic ratchet in the backtest. A volatility switch that halves size on a signal is that ratchet. Appendix G at 2% risk had a lower CAGR and a deeper drawdown than the 1% book. Scaling risk up when volatility is low would also require buying power this cash account does not use.

**The specification that is written down so it is not reinvented, and is not run.** No realized-vol window, no median cutoff, and no half-risk state is added to the checklist or the harness. Risk stays a constant in the backtest variants that already exist. The operator's 0.005 setting remains the Q7 probation, counted from `book.jsonl` closes, and it is not a function of SPY.

## Connors RSI(2) stays the third setup

The live rule is Wilder RSI(2) strictly below 10, and the stock's close above its SMA(200). The mutex only reaches it when breakout and pullback did not fire. The exit is the same 1.5×ATR stop and 2R target as the other two setups. Redesign section A3 keeps the threshold at 10 and keeps it off the role of sole trigger. Variant L (RSI2 only, inside the trail book) was weaker than the all-trigger book in Appendix A.

The published Connors shape, from StockCharts' RSI(2) note and from the EasyLanguage write-up of the cumulative version, is a different trade: price above the 200-day average, buy on the close when RSI(2) or cumulative RSI(2) is below 5, exit when the close is above the 5-day average, and no hard stop. StockCharts also records the short side: below the 200-day average, short when RSI(2) is above 95, cover below the 5-day average. Connors' own comparison, as restated there, found a dip below 5 paid more in his test than a dip below 10.

Those extensions stay out. A short is forbidden. A no-stop entry breaks the 1% risk contract. A buy-the-close fill is not the next-open plan this CLI prints. An SMA(5) exit is a new exit rule, and Q2 already froze the unshipped exit as a 3×ATR trail with 2R only as a selectable v1 mode. The live book keeps 2R until a later gate passes. RSI(2) stays third in the mutex, at 10, with the stop.

## Products that encode the same ideas

| Product | What it encodes | Fit for this CLI |
|---|---|---|
| Faber GTAA | 10-month SMA on five asset classes, out-of-market sleeve in T-bills | The equity timing rule is the Q3 family. Bonds, commodities, and REITs are outside the lock. T-bill yield is interest. |
| Antonacci dual momentum / GEM | 12-month relative momentum between equity indexes, absolute momentum versus T-bills, defensive sleeve in aggregate bonds | Index rotation, not a swing ticket. The defensive sleeve is interest. |
| Jegadeesh-Titman, and French Mom | Decile or 30/70 long-short momentum on a broad US cross-section | The short leg is forbidden. The user's list is not that cross-section. The unshipped 126/5 rank is the version this repo already measured. |
| IBD Relative Strength Rating | A 1–99 percentile of 12-month price performance versus the whole market, with a heavier weight on the most recent three months. IBD's page says prefer 80 or higher, and cites an internal study whose average winner started at 87. The RS line is a separate series, the stock versus the S&P 500. | Proprietary. Importing the rating would rank the user's names by a vendor score this CLI does not compute, and would act as a second screen. The 87 figure is IBD's own study, not a costed test on this harness. |
| CAN SLIM | O'Neil's mix of earnings, annual growth, new-high behavior, supply and demand, leadership, sponsorship, and a market-direction call. IBD's routine page checks direction from The Big Picture / Market Pulse. | The fundamental letters would be a screening method. The universe file is the user's screen. The market call is a discretionary label, not a frozen price rule. |
| Connors RSI(2) | Short-horizon mean reversion, long and short, often with no hard stop | Already present in narrowed form. The published extras stay out. |

No long-only swing system read for this note is a cash USD equity book, with a hard stop, with costs, on a survivorship-free universe, that this CLI could adopt in place of v0. Faber and Antonacci time an index. Jegadeesh-Titman and French sell losers. Connors trades a different exit. IBD sells a rating. The closest swing numbers this repo has are its own: in Appendix A.1 the three v0 entries did not beat random-day entries on the same stop and target (+0.133R versus +0.164R), and the v1 package lost the ship gate.

## Anti-list

These stay out. They are not bake-offs.

| Idea | Why it stays out |
|---|---|
| Flip `swing analyze` to the v1 ranker | The 2014 random-rank Sharpe is higher. ADR 0002 and Section 8 already record that. `analyze` does not import `VARIANTS`. |
| More confirmation indicators | The three live setups share one stop and one target. Another oscillator would be a new parameter on a checklist that has not beaten a random entry. |
| Turtle pyramiding | The turtle systems add units as price moves in their favor, long and short, on futures. Adding to a winner raises exposure in a cash account that already sizes off a 1% stop. Pyramiding is not in the pre-registered variants. |
| Short-term reversal deciles | Jegadeesh and Titman set the one-week and one-month horizon aside as reversal, and studied 3–12 months instead. v0 already turns over about 90 trades a year. A reversal decile raises that turnover and needs the short leg for the published spread. |
| Qullamaggie episodic pivot or opening-range breakout | Those are intraday opening-range trades, usually on a news gap. This CLI's signal is the last completed daily bar, and the planned fill is the next open. An opening range is not in the daily bar. |
| Minervini VCP as a new live setup | The volatility-contraction pattern is a chart judgment layered on fundamentals (SEPA). It would be a fourth setup and a screen. The mutex stays three setups. |
| Volatility targeting up | Moreira-Muir and the Cederburg replication scale by the inverse of lagged variance, which levers above one when volatility is low. Cederburg's real-time versions do not systematically beat the unmanaged book. Leverage is a margin loan. `account.mode` is cash only. |
| Options, CFDs, margin, pairs | Locks: cash, long equity or ETF, USD. No shorts, so no pair. No options or CFDs. |
| Post-earnings drift as an entry | Martineau's abstract (SSRN 3111607): for large stocks, post-earnings drift has been absent since 2006. Q8's rule is the opposite: do not hold a single stock through a report. v0 keeps the entry blackout. |
| "AI finds the pattern" | Decisions stay the checklist. News, model output, and sentiment do not enter the gates. A discovered pattern would be a search on the same sample the ship rule already refused to tune. |

## Conflicts with `docs/decisions/SECTION8_ANSWERS.md`

These are disagreements between the proposed upgrades and decisions that stay in force. This note does not edit Section 8.

1. **Q3 already chose the trend gate.** Hard stop on new entries when SPY's close is at or below SMA(200). Faber 10-month is that rule in monthly form. Antonacci's 12-month excess return versus T-bills, and the bond sleeve behind it, is a different rule and an interest-bearing asset. Testing either one, or blocking when either one fails, retunes `regime.sma` and the definition of "out." Q3 also rejected half-size as an unregistered parameter.
2. **The gate was already inside the failed ship package.** v1 used `regime.sma = 200` and lost on 2014 Sharpe to random rank. Section 8 says that gap is not a reason to retune the regime gate. Appendix A's on/off comparison was mixed, and the reproduction broke the ±2 CAGR band on the 2021 no-gate book.
3. **Q1's cash is not Faber's or Antonacci's cash.** The satellite can sit in cash while the core ETF stays invested. The published timing results collect T-bill or bond returns in the "out" state. Those returns are interest. They are not the satellite's uninvested cash, and they are not a reason to hold SPY, T-bills, or aggregate bonds in this account. SPY remains a timing series only.
4. **The rank window stays 126 and 5.** Upgrade 2 replaces that with a 12-month return skipping a month, and replaces the sort with a top-half membership test. Section 8 lists the rank window among the knobs not to retune. Q13's 20-name floor is also why a quartile cutoff does not get a silent pass: on a 30-name list it leaves fewer names than Q13 treats as a usable rank.
5. **Q4's 1993 attribution is looser than the 2001 paper.** The five-dollar exclusion is explicit in Jegadeesh and Titman's 1999 NBER draft of the 2001 paper, which presents it as a tightening relative to the 1993 series. Q4 cited a restatement that assigns the screen to 1993. The default `liquidity.min_price = 5` stays, for the 2001 screen and for the rest of Q4's reasons. The live checklist still has no dollar floor. This note does not add one.
6. **Q7's half-size is not a volatility function.** It is `0.005` until 20 closed real fills, then `0.01`, edited by hand in `~/.swing/config.toml`. Section 8 forbids an automatic ratchet. Upgrade 3 is that ratchet, keyed off SPY. Appendix G is the evidence on file that raising risk above 1% hurt.
7. **Q9's next harness run is the old list.** After a delisted file arrives, rerun the pre-registered variants and the v1 gate. Do not search parameters on the new file. These three upgrades are not added to that list.
8. **The live checklist stays v0.** Wiring any of the three into `ChecklistBrain` would change built-in behavior Section 8 locked. `gates["regime"] = "pass"` stays a pass until a future ship gate, which this note does not open.

## What a later session inherits

- Live `swing analyze` stays on v0.
- v1 stays a backtest variant. It is not promoted because a peer-system paper exists.
- No new variant name, no new config key, no new indicator.
- Success metric P2 is unchanged: unproven until mean trade R minus two standard errors is above zero after at least 100 closed trades, and the sleeve is ahead of the benchmark over at least 12 months.

## Sources

Accessed 2026-10-03 unless noted.

Faber, Meb. "A Quantitative Approach to Tactical Asset Allocation." PDF of SSRN 962461: <https://mebfaber.com/wp-content/uploads/2016/05/SSRN-id962461.pdf>

Antonacci, Gary. "Risk Premia Harvesting Through Dual Momentum." SSRN abstract 2042750: <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2042750> (PDF blocked on this pass)

Antonacci, Gary, interviewed by Meb Faber, 23 March 2017, published 29 March 2017: <https://mebfaber.com/2017/03/29/episode-45-gary-antonacci-get-synergy-happens-use-dual-momentum/>

Antonacci, Gary. Optimal Momentum FAQ: <https://www.optimalmomentum.com/faq/>

Jegadeesh, Narasimhan, and Sheridan Titman. "Returns to Buying Winners and Selling Losers." *Journal of Finance* 48 (1993). PDF: <https://www.bauer.uh.edu/rsusmel/phd/jegadeesh-titman93.pdf>

Jegadeesh, Narasimhan, and Sheridan Titman. "Profitability of Momentum Strategies: An Evaluation of Alternative Explanations." NBER working paper 7159 (1999): <https://www.nber.org/system/files/working_papers/w7159/w7159.pdf>

French, Kenneth R. Detail for the monthly momentum factor: <https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_mom_factor.html>

Daniel, Kent, and Tobias J. Moskowitz. "Momentum Crashes." *Journal of Financial Economics* 122 (2016). PDF: <https://www.kentdaniel.net/papers/published/jfe_16.pdf>

Cederburg, Scott, Michael S. O'Doherty, Feifei Wang, and Xuemin (Sterling) Yan. "On the Performance of Volatility-Managed Portfolios." *Journal of Financial Economics* 138 (2020). PDF: <https://www.lehigh.edu/~xuy219/research/COWY.pdf>

Martineau, Charles. "Rest in Peace Post-Earnings Announcement Drift." SSRN 3111607: <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3111607>

Investor's Business Daily. "What Is Relative Strength?": <https://www.investors.com/how-to-invest/investors-corner/what-is-relative-strength/>

Investor's Business Daily. "How To Invest: 3-Month Relative Strength Rating": <https://www.investors.com/how-to-invest/investors-corner/how-to-invest-in-stocks-relative-strength/>

Investor's Business Daily. "Time-Saving Routine Using IBD": <https://www.investors.com/ibd-university/getting-started/routine/>

StockCharts ChartSchool. "RSI(2)": <https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/rsi-2>

EasyLanguage Mastery. "Connors 2-Period RSI Update for 2016": <https://easylanguagemastery.com/strategies/connors-rsi-update-2016/>

In-repo evidence, not re-simulated on this pass: `docs/backtests/v1-gate.md`, `docs/REDESIGN_PLAN.md` Appendix A, `docs/decisions/SECTION8_ANSWERS.md`.
