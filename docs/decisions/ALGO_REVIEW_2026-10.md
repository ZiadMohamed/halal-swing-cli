# Algorithm review — 5 October 2026

Live `swing analyze` stays on v0. I did not change a stop, a target, a setup, or a size rule. I did not search parameters. The ship rule is the one already written in `docs/backtests/v1-gate.md`: a new book has to beat v0 on yearly growth and on Sharpe in both windows, and it has to beat its own random-rank twin on those same two numbers. Sharpe here means yearly growth divided by how bumpy the path was. A higher Sharpe is a smoother path for the same growth, or more growth for the same bumpiness.

v1 is the book that beats v0. It still fails that rule. The published systems that look stronger than v0 are a different trade: they hold for months, they sell stocks short, or they park the spare cash in Treasury bills. None of those is a cash, long-only, days-to-weeks ticket with a hard stop. They do not get switched on.

Words, once:

- **Close**: the last price of the day.
- **Average / SMA(N)**: the plain average of the last N daily closes. SMA(50) is the 50-day average. SMA(200) is the 200-day average.
- **Smoothed line / EMA(N)**: an average that weighs recent days more than old days. EMA(20) is the 20-day smoothed line.
- **ATR(14)**: the average daily range over 14 sessions. "Range" means how far price traveled that day, including a gap from yesterday's close. It is not a direction.
- **R**: the distance from the buy price to the stop. A 2R profit price is twice that distance above the buy. A trade that loses 1R lost the amount you planned to risk.
- **RSI(2)**: a 0–100 score of the last two days. Low means those days were down days. High means they were up days.
- **CAGR**: the compound yearly growth rate. A single number for "what percent a year, compounded."
- **Sharpe**: CAGR divided by how much the account value jumped around. Higher is a calmer path for the growth you got.
- **Max DD**: the worst peak-to-trough drop in the account.
- **Long-short**: buy the winners and sell borrowed shares of the losers. This CLI does not sell short. A published long-short profit is not a profit this account can copy.

## What was already on file

I read `docs/REDESIGN_PLAN.md`, `docs/decisions/SECTION8_ANSWERS.md`, `docs/decisions/PEER_SYSTEMS.md`, `docs/backtests/v1-gate.md`, `docs/backtests/appendix-a-reproduction.md`, and ADR 0002 before this pass. Those notes already did the following, so this file does not re-measure them:

- On the same stop and the same 2R profit price, the three v0 entries made **+0.133R** a trade. A random day made **+0.164R**. A random day while the close was above the 200-day average made **+0.142R**. The setups did not beat "buy a random day." That is Appendix A.1 of the redesign plan.
- Replacing the 2R profit price with a trail of 3 times ATR raised the 2021 portfolio from 7.71% to 11.93% a year in that same appendix (variants C/M versus D2). The reproduction kept the trail ahead (9.67% versus 8.04%).
- v1 bundled the trail, a momentum rank, a market filter, an exit before earnings, five slots, and a 20% cap. It beat v0. It lost the 2014 Sharpe comparison to a random rank of the same signals. Section 8 and ADR 0002 left the live checklist on v0 and said not to retune the rank window, the trail, the slot count, or the market filter to flip that gap.
- Peer-system note of 3 October 2026 skipped a second market filter (Faber 10-month average, Antonacci 12-month switch into bonds), a "top half of the list" rank, and a volatility cut that halves size. Those stay skipped. Faber and Antonacci earn interest while they are out of stocks. This satellite earns nothing on idle cash. The bond sleeve is interest. This account does not hold it.

I did not re-run `swing backtest`. The command refuses to download. This checkout has no price cache. A fresh download would be a different sample, not a new reading of the gate. The gate numbers below are the ones already in `docs/backtests/v1-gate.md`, from the run where no parameter was changed afterward.

| Window | Book | CAGR % | Sharpe | Max DD % |
|---|---|---:|---:|---:|
| 2021-01-04 → 2026-09-30 | v0 | −9.93 | −0.73 | −49.45 |
| 2021-01-04 → 2026-09-30 | v1 | 13.67 | 0.96 | −22.15 |
| 2021-01-04 → 2026-09-30 | v1 random rank | 4.96 | 0.50 | −18.52 |
| 2014-06-02 → 2026-09-30 | v0 | 5.86 | 0.50 | −30.20 |
| 2014-06-02 → 2026-09-30 | v1 | 12.74 | 0.90 | −24.43 |
| 2014-06-02 → 2026-09-30 | v1 random rank | 10.55 | 0.95 | −21.89 |

v1 wins growth and Sharpe against v0 in both windows. v1 wins growth against its random-rank twin in both windows, and wins Sharpe in 2021 (0.96 versus 0.50). In 2014 the random twin's Sharpe is higher by 0.05. That one miss is the ship rule. The sample is today's large caps, which inflates a momentum rank. Earnings dates are missing before 2020, so the 2014 window does not use the earnings exit. The reproduction also missed several appendix growth rates by more than 2 points. None of that is a reason to nudge 3.0 ATR to 2.8 until the gap flips.

Buy-and-hold of SPUS, the screened fund the plan uses as the comparison, was 17.61% a year in Appendix A and 17.24% in the reproduction over 2021–2026. Every swing book in those tables was lower. That comparison stands.

## What this pass read

The question was: for cash, long-only US stocks, daily bars, a hold of days to weeks, and orders typed by hand, is there a published system that beats this ticket?

### The old breakout and moving-average rules do not survive a fair test

Brock, Lakonishok, and LeBaron (Journal of Finance, 1992) tested the two simplest chart rules on the Dow from 1897 to 1986. One rule is "buy when the short average crosses above the long average." The other is a trading-range break: buy when price clears the recent high, sell when it breaks the recent low. Their abstract says buy signals made more than sell signals, and the days after sell signals were negative. That break rule is the ancestor of v0's volume breakout (close above the prior 20-session high), minus the volume check and minus the short side.

Sullivan, Timmermann, and White (Journal of Finance, 1999) took that study, expanded 26 rules to 7,846, and corrected for the fact that someone had already picked the rules that looked good. Inside the original years, the best rule still beat the benchmark after that correction. In the next 10 years, the best rule did not.

Bajgrowicz and Scaillet (Journal of Financial Economics, 2012) ran those 7,846 rules on the Dow from 1897 to 2011. Even the looser "keep every rule that looks good" test could not pick, ahead of time, which rules would win next. Low trading costs wiped out the in-sample profit. Their conclusion is that the economic value claimed for those early chart rules does not hold up.

So the pattern "close above the recent high" has a famous paper behind it, and the careful follow-ups say the profit was the sample and the costs. That matches this repo. On the same stop and the same 2R price, random days beat the three setups.

### The long-only stock trend that has a real test holds for about a year

Wilcox and Crittenden, "Does Trend Following Work on Stocks?" (2005, the PDF hosted at the University of Pennsylvania link below). They bought when a US stock closed at an all-time high and sold at the next open after a trail of 10 average daily ranges was hit. The database was 24,000-plus names from 1983 to 2004, including delisted names, with a price floor and a liquidity floor applied as of that day. Costs were 0.5% round-trip. More than 18,000 trades. Win rate 49.3%. Average result about 15.2% a trade. Average hold **305 calendar days**. They also tried trails from 8 to 12 times the range and said the middle setting was not special. That is their search, reported here as they wrote it, not a search I am opening.

Their later portfolio chart is labeled against the S&P 500 total return and prints 19.3% a year compounded next to 12.0%, with a worst drop of −20.8% next to −44.7%. The sizing rules of that portfolio are not in the paper. The 19.3% is not the raw "buy every new high" result. It is an undisclosed wrapper on top of the entry and the trail.

Zarattini, Pagani, and Wilcox, "Does Trend-Following Still Work on Stocks?" (SSRN 5084316; the February 2026 PDF on concretumgroup.com). Same idea, extended. About 31,000 common stocks from 1950 through October 2024, about 24,000 of them delisted, more than 66,000 trades, 0.5% round-trip on the trade study. Less than 7% of the trades produce the cumulative profit. Win rate 43.90%. Average winner 1.90R, average loser −0.70R. Winning trades last about **370 days**. The stop is a trail of about 10 average ranges under the all-time high, using a 42-day range, and it never moves down. Out of the original sample (2005–2024) the shape still made money, with a smaller average trade.

The portfolio they then built is not that trade list. It is Russell 3000 names, price above $10, average dollar volume above $1 million, buy the next open after a new all-time high, size so each name contributes the same volatility, target 30% annualized volatility for the book. From 1991 to 2024 the version with no costs, no slippage, fractional shares, and no interest shows **15.02%** a year and an alpha of **6.19%** a year against the market. Alpha here means the extra yearly return after accounting for how much the book moved with the market.

Put costs, slippage, and interest on a **$100,000** account and that 15.02% falls to **2.45%**, and the alpha turns to **−4.63%**. At $1 million it is 9.01% with a small positive alpha. They then describe a turnover control that lifts the $100,000 book to 12.97% (Sharpe 0.75). The control is not specified in the paper. The text says to email them for it. The same paragraph says the book runs at about 120% of equity, which is borrowed money. This CLI is cash. A 20% satellite is much smaller than $100,000 of trend capital. The costed $100,000 result is the one that matches the account size, and it loses to both v1's 13.67% on the survivor sample and to SPUS buy-and-hold.

This is the clearest published long-only stock system I found. It beats a fixed 2R cap by letting a few huge winners run for a year. It is not a swing ticket. A 10-range stop is many times v0's 1.5-range stop. Sized at 1% of the sleeve to that stop, the share count collapses. Sized like their volatility book, the account borrows. I am not shipping it.

### A 10-day average on volatile portfolios beats buy-and-hold, and the spare money earns interest

Han, Yang, and Zhou, "A New Anomaly: The Cross-Sectional Profitability of Technical Analysis" (Journal of Financial and Quantitative Analysis, 2013; the PDF I read is the one on Kevin Sheppard's page). NYSE and AMEX stocks sorted into ten portfolios by volatility, July 1963 through December 2009. Rule: hold the portfolio when yesterday's price is above its 10-day average, otherwise hold the 30-day Treasury bill. The gap versus just holding the portfolio runs from **8.42% to 18.70% a year** across those ten portfolios, larger for the more volatile ones, and they say it survives costs.

The spare cash is a Treasury bill. That is interest. This satellite's idle cash is not a T-bill. The rule can flip every day. A 10-day average on a portfolio is not "buy one stock, hold it for one to three weeks, stop 1.5 ranges under the close." The result is real. It is not this product. Peer systems already rejected Faber's and Antonacci's interest-bearing "out" state for the same reason. This paper is the stock version of that same shape.

### Ranking beats a recent-return sort, on a market this CLI does not trade

George and Hwang, "The 52-Week High and Momentum Investing" (Journal of Finance, 2004). Being near the high of the past year explains more of the momentum profit than the usual "past six months" return. In their head-to-head, a self-financed book that buys the top 30% and shorts the bottom 30% made **0.65% a month** from the 52-week high, against **0.38%** for the Jegadeesh-Titman past-return book and **0.25%** for an industry book. Outside January the 52-week-high book was **1.06% a month** against 0.46% and 0.22%. Those are long-short spreads on the whole CRSP market, held for six months, from the regressions in that paper. Drop the short side and the spread is not the published number. Daniel and Moskowitz (2016), already in the peer note, put the crash of that strategy on the short side.

Novy-Marx, "Is Momentum Really Momentum?" (Journal of Financial Economics, 2012), as restated by Wiest (Financial Markets and Portfolio Management, 2022) from the paper: from 1927 to 2010, sorting on months 12 through 7 made **1.20% a month**. Sorting on months 6 through 2 made **0.67% a month**. Both are long-short. The recent window is the weaker one, and it is the window v1 uses (about six months, skipping a week: close five sessions ago divided by close 126 sessions ago, minus one). Wiest also notes the result survives the usual size, value, and momentum adjustments in that paper.

Moskowitz, Ooi, and Pedersen, "Time Series Momentum" (Journal of Financial Economics, 2012). An instrument's own past 12-month excess return predicts the next month. They found it on all 58 futures and forwards they looked at (equity indexes, currencies, commodities, bonds), and the effect fades after about a year. That is a futures book, long and short, not a single US stock with a 1.5-range stop.

v1's rank is the weaker of Novy-Marx's two windows, on a list of 50 survivors, and it already lost a Sharpe comparison to a coin flip. Changing 126 sessions to "12 months through 7 months" on that same list, in order to clear a 0.05 gap, is the retune Section 8 forbade. I am not running it. The specification is written at the end so the next session does not invent a third window.

### What this repo measured is still the only test of this stop and this profit price

Appendix A.1, same stop, same 2R price, one trade per name at a time, 2013–2026, 50 current large caps:

| Entry | Trades | Mean R | Win % | Typical hold |
|---|---:|---:|---:|---:|
| v0's three setups | 7,346 | +0.133 | 39.5 | 8 sessions |
| Random day | 9,569 | +0.164 | 40.5 | 8 sessions |
| Random day, close above the 200-day average | 6,948 | +0.142 | 39.8 | 8 sessions |

On those same v0 entries, an exit when the close crosses the 5-day average made **−0.012R**. A 10-session time stop made **+0.049R**. The stop-or-2R exit made **+0.132R**. Larry Connors' published dip trade often exits at the 5-day average and often has no hard stop. On these entries, that exit was worse. Peer systems already refused to swap the exit. This pass agrees, with the number that is already in the appendix.

The portfolio numbers that beat v0 are the ones in the gate table above, and they belong to v1, which failed the random-rank Sharpe test.

## Why each live piece is there

v0 is one ticket. Three detectors, one stop, one profit price, one size. The detectors are labels. They do not change the dollars.

### Volume breakout, first in line

The close is above the 50-day average, above the highest high of the prior 20 sessions, and volume is at least 1.5 times the average volume of those prior 20 sessions (today's volume is not in that average). The 20-session high is the trading-range break from Brock and from the old Donchian channel, shortened to a month of sessions because this book wants days to weeks, not the year-long all-time-high trade above. The 50-day average keeps the break on the same side as the recent trend. The 1.5 volume multiple is a confirmation the academic break rule did not require. It is a round number, not a fitted one. The mutex puts this label first when more than one setup is true on the same day. The share count does not change.

It was chosen because a close through a month's high, on heavier volume, is a pattern a person can check on a chart before typing the order. It was not chosen because it beat a random day. It does not.

### Pullback to the 20-day smoothed line, second

The close is above the 50-day smoothed line. The day's low tags the 20-day smoothed line. The close finishes back above that line. This is the standard "buy a dip inside an uptrend" shape used by short-term stock traders: the longer line says the trend is up, the shorter line is the place the dip is supposed to stop. I did not find a journal paper that reports a CAGR for this exact pair of lines with a 1.5-range stop and a 2R price. It is in the mutex so a clean breakout is named first, and a dip is still a ticket when the breakout is not. Same stop, same profit price, same size. The label is the only difference.

### Two-day dip above the 200-day average, third

Wilder RSI(2) is strictly below 10, and the close is above the 200-day average. This is Connors' dip, narrowed. His published version, as the peer note already recorded from StockCharts and the EasyLanguage write-up, buys when RSI(2) is below 5, often exits when the close is back above the 5-day average, often uses no hard stop, and also sells short below the 200-day average. v0 uses 10 instead of 5, refuses the short, and uses the same 1.5-range stop and 2R price as the other two setups. The 200-day average is there so the dip is only bought in a stock that is still above its long average. The redesign's own portfolio test of "this setup alone" was the weak book (Appendix L, 4.46% a year in 2021 against 11.93% for all three triggers inside the trail book). It stays a trigger, not the system.

The threshold 10, rather than Connors' 5, was a locked preference so the dip fires more often. It was not retuned. Making it 5 now, to chase the original pamphlet, would be a new parameter on an entry that already lost to a random day.

### The stop: 1.5 times the 14-day range under the close

ATR(14) is Wilder's measure of a normal day's travel. Multiplying by 1.5 puts the stop outside one ordinary day and inside a move that is still small enough to size. The 1.5 is a round number. It was not optimized. Appendix A says about 10% of trades gap through it, those gaps average −1.28R, and the worst was −7.27R. A stop on a daily bar does not contain an overnight gap. That is why the earnings blackout exists, and why v1's stronger rule (get out the session before the report) cut the worst loss from −6.51R to something the cap could bound. The live rule only blocks entries in a short window around the report. It does not force a sale of a stock you already hold. That stronger exit is inside the unshipped v1 book.

### The profit price: twice the stop distance above the close

2R is there so one winner pays for two losers, which is the arithmetic of a system that wins a bit more than one time in three. The measured win rate on these entries was about 40%, so the arithmetic is in the right neighborhood, and the mean was still only +0.13R. The price is a cap. It cuts off the few huge winners that the Wilcox and Zarattini studies say are the entire profit of a trend book. The harness agrees: the 3-range trail beat the 2R book on growth in both windows (Appendix D2 versus M: 11.93% versus 7.71% in 2021, 13.50% versus 12.04% in 2014; the reproduction kept that order). The trail's win rate is about 35–39%, which looks worse and makes more money because the winners are larger. v0 keeps the cap because the trail was shipped only as part of v1, and v1 failed the gate. I am not turning the trail on by itself. A trail-only change is a new book, and it was not given its own random-rank test in the gate file.

### The share count: 1% of the sleeve to the stop

Shares are the sleeve times 0.01, divided by the dollars from the close down to the stop, rounded down. That is Van Tharp's "one trade cannot dominate": you risk about 1% of the sleeve if the stop fills. Appendix G doubled it to 2% and got a lower growth rate and a deeper drop (7.20% versus 7.71%, drawdown −37% versus −29% in the 2021 appendix). The 1% stays.

The live formula does not look at cash. Appendix A says the median position was **31.8% of the sleeve**, 72% of trades were above 25%, and 10% were above 50%. Four of those do not fit in a cash account. If all four get typed, the broker can only fill them by lending, and this product is not a margin product. The measured fix is v1's cap of 20% of the sleeve and five slots, which is inside the book that failed the 2014 Sharpe test. I am not turning the cap on alone. Splitting one rule out of a failed package, without a new pre-registered run, is how a gate gets talked around. The defect is real. The live ticket can still print a share count a cash account cannot fund. The operator has to look at the dollars and not type a buy the cash cannot pay.

### The mutex, the blackout, and the four-position cap

The order is breakout, then pullback, then dip. All three share the stop, the profit price, and the size, so the order only picks a name. It was kept so the card can say one setup.

The earnings blackout is the entry day plus the two sessions before the report and the one session after, on NYSE sessions. It exists because a report can gap through any 1.5-range stop. It is weaker than "sell the day before the report," which won in the appendix (holding through the report was 5.78% versus 7.71% for getting out). The stronger rule is v1. It is not live.

Four positions and the heat caps are the old book. Four times 1% is 4% of the sleeve at risk to the stops, so the 6% heat cap never binds. The binding problem is the cash, above, not the heat number.

## Verdict

v0 is a clear ticket a person can type. It is not an edge over buying a random day with the same stop and the same profit price. The setups were chosen because they are recognizable and because they share one risk contract, not because they won a test.

What beats v0 on this repo's own harness is v1: about **23 percentage points** a year better in the 2021 window (−9.93% to 13.67%) and about **7 points** better in the 2014 window (5.86% to 12.74%), with a better Sharpe in both (0.96 versus −0.73, and 0.90 versus 0.50) and a smaller worst drop. The random-rank twin of that same book made 4.96% (Sharpe 0.50) in 2021 and 10.55% (Sharpe 0.95) in 2014. v1's extra growth over a coin flip is large in 2021 and about 2 points in 2014. The 2014 Sharpe loss is 0.05. The rule says that is a miss. I agree with the rule. A survivor list inflates the rank, which is the piece that is supposed to be the edge, and the random twin beat it on the risk-adjusted number in the longer window. Shipping v1 because the growth looks better would throw out the control the gate was built to require.

What beats a 2R cap in the published long-only stock literature is the all-time-high trend with a trail of about 10 daily ranges. Wilcox: about 15.2% a trade, 305-day hold, 1983–2004, delisted names included. Zarattini, Pagani, and Wilcox: the shape still pays after 2005, winners last about a year, and a costed $100,000 portfolio of the practical version earns **2.45%** a year against a no-cost 15.02%. That 2.45% does not beat v0's 2014 book (5.86%), does not beat v1, and does not beat SPUS. The no-cost 15% and the undisclosed 19.3% are not numbers this account can have. I will not swap the live stop to 10 ranges or the hold to a year.

Han, Yang, and Zhou's 8 to 19 points a year over buy-and-hold is a 10-day switch into T-bills. The interest is not available as the "out" state of this satellite, and the hold is a day, not a week.

George and Hwang's extra 0.27 points a month over Jegadeesh-Titman (0.65 minus 0.38), and Novy-Marx's 1.20% versus 0.67% a month, are long-short results on the whole market. They say the rank window inside unshipped v1 is the weaker published window. They do not say a one-ticker checklist should change.

No live rule changes.

## The next test, written down so it is not reinvented

Do not run this until a delisted US price file is on the machine (the Sharadar choice in Section 8). Do not search. One new book, plus the books the gate file already has, on that file, once.

**Book name:** `intermediate`. Not live. Not a config key today.

- Same cash, long-only, no-short rules.
- Entry triggers stay the three v0 detectors. Do not add an all-time-high setup in the same run. That would mix two questions.
- Rank by the intermediate window only: close about 7 months ago divided by close about 12 months ago, minus one. In sessions that is close at t−147 divided by close at t−252, minus one. Skip the most recent 7 months instead of the most recent week. This is the Novy-Marx window, not a search around it.
- Everything else stays the recorded v1 book: trend filter, market filter, earnings exit, five slots, 20% cap, 1.5-range initial stop, 3-range trail, 1% risk, $5 and $10 million liquidity floors, 1-range entry cap.
- The control is the same book with random rank, seed 42.
- Ship only if `intermediate` beats v0 on CAGR and Sharpe in both windows and beats that random twin on both numbers in both windows. If it misses, leave v0 and do not try 11 months or 8 months.

I did not run `intermediate`. There is no cache here, and running it on the survivor list to see if 0.05 flips would be the search this file is refusing.

The all-time-high, 10-range, year-long book is not on that list. The 2025 paper already priced it at 2.45% a year after costs on $100,000, before any borrow. Another backtest of it on 50 living large caps would not teach more than that.

## universe.txt

Removed. `swing analyze TICKER` never read it. `swing backtest` reads a parquet cache path, not that file. `swing today` only printed a nag when the file was missing, and it never ranked the names. `MassiveBarProvider.load_universe` takes a list of tickers from the caller. No command passed it `universe.txt`. Doctor treated a missing file as a failure and lectured about a 20-name floor that blocked nothing. The ETF tag in the file was unused. Instrument type still comes from the vendor.

The redesign notes and Section 8 still describe the file, because they describe a scan that was never built. Those files are the record of that plan. The current behavior is the README: there is no universe file, and doctor does not look for one.

## Sources

Read for this pass, 5 October 2026, unless the date is in the citation.

Brock, William, Josef Lakonishok, and Blake LeBaron. "Simple Technical Trading Rules and the Stochastic Properties of Stock Returns." *Journal of Finance* 47 (1992). <https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.1992.tb04681.x>

Sullivan, Ryan, Allan Timmermann, and Halbert White. "Data-Snooping, Technical Trading Rule Performance, and the Bootstrap." *Journal of Finance* 54 (1999). The in-sample versus next-decade result is from the paper's own summary as carried on the ResearchGate record of that article. <https://onlinelibrary.wiley.com/doi/10.1111/0022-1082.00163>

Bajgrowicz, Pierre, and Olivier Scaillet. "Technical trading revisited: False discoveries, persistence tests, and transaction costs." *Journal of Financial Economics* 106 (2012). <https://ideas.repec.org/a/eee/jfinec/v106y2012i3p473-491.html>

Wilcox, Cole, and Eric Crittenden. "Does Trend Following Work on Stocks?" 2005. PDF: <https://www.cis.upenn.edu/%7Emkearns/finread/trend.pdf>

Zarattini, Carlo, Alberto Pagani, and Cole Wilcox. "Does Trend-Following Still Work on Stocks?" SSRN 5084316. PDF read: <https://concretumgroup.com/wp-content/uploads/2026/02/Does-Trend-Following-Still-Work-on-Stocks.pdf>

Han, Yufeng, Ke Yang, and Guofu Zhou. "A New Anomaly: The Cross-Sectional Profitability of Technical Analysis." *Journal of Financial and Quantitative Analysis* (2013). PDF read: <https://www.kevinsheppard.com/files/teaching/mfe/advanced-econometrics/Han_Yang_Zhou.pdf>

George, Thomas J., and Chuan-Yang Hwang. "The 52-Week High and Momentum Investing." *Journal of Finance* 59 (2004). PDF: <https://www.bauer.uh.edu/tgeorge/papers/gh4-paper.pdf>

Novy-Marx, Robert. "Is Momentum Really Momentum?" *Journal of Financial Economics* 103 (2012). The 1.20% and 0.67% monthly figures are taken from Wiest's restatement of that paper, not from a re-computation. <https://ideas.repec.org/a/eee/jfinec/v103y2012i3p429-453.html>

Wiest, Tobias. "Momentum: what do we know 30 years after Jegadeesh and Titman's seminal paper?" *Financial Markets and Portfolio Management* (2022). <https://link.springer.com/article/10.1007/s11408-022-00417-8>

Moskowitz, Tobias J., Yao Hua Ooi, and Lasse Heje Pedersen. "Time Series Momentum." *Journal of Financial Economics* 104 (2012). PDF: <https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf>

In-repo numbers, not re-simulated: `docs/backtests/v1-gate.md`, `docs/backtests/appendix-a-reproduction.md`, `docs/REDESIGN_PLAN.md` Appendix A, `docs/decisions/SECTION8_ANSWERS.md`, `docs/decisions/PEER_SYSTEMS.md`.
