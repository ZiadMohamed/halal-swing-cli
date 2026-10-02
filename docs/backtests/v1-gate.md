# v1 ship gate

Same sample and cost model as [appendix-a-reproduction.md](appendix-a-reproduction.md). v0 is variant A (the current checklist: all three triggers, random rank, 2R, no notional cap, no regime gate, entry blackout). v1 is Section 6.4: SMA(200) trend on every trigger, momentum rank, SPY regime gate, earnings exit, 5 slots, 20% cap, 1×ATR entry cap, $5 and $10M liquidity floors, 260 sessions, 3×ATR trail. v1_random is that book with random rank, seed 42.

No parameter was changed after this run.

## 2021-01-04 → 2026-09-30 (earnings on)

| Book | CAGR % | Sharpe | Max DD % | trades/yr |
|---|---:|---:|---:|---:|
| v0 (A) | −9.93 | −0.73 | −49.45 | 91.5 |
| v1 | 13.67 | 0.96 | −22.15 | 77.1 |
| v1 random rank | 4.96 | 0.50 | −18.52 | 73.7 |

## 2014-06-02 → 2026-09-30 (earnings off; dates before 2020 are missing)

| Book | CAGR % | Sharpe | Max DD % | trades/yr |
|---|---:|---:|---:|---:|
| v0 (A) | 5.86 | 0.50 | −30.20 | 89.3 |
| v1 | 12.74 | 0.90 | −24.43 | 60.3 |
| v1 random rank | 10.55 | 0.95 | −21.89 | 57.0 |

## Decision

v1 beats v0 on CAGR and Sharpe in both windows. v1 beats its random-rank baseline on CAGR in both windows and on Sharpe in 2021 (0.96 vs 0.50). In the 2014 window the random-rank book has the higher Sharpe (0.95 vs 0.90).

The ship rule requires v1 to beat that baseline, and Sharpe is one of the two gate metrics. The live checklist is unchanged. Nothing was tuned to try to flip the 2014 Sharpe.
