# Appendix A reproduction

Run on 2026-10-02 with `swing backtest` rules: yfinance auto-adjusted daily bars, 2013-01-01 through 2026-10-01, the 50-ticker survivor list in Appendix A, earnings dates from yfinance (`get_earnings_dates`, kept from 2020), fills at the next open, stop gaps at the open, trail updated after the bar, $1 plus 5 bps per side, T+1 settlement, $100,000 start. Random variants use seed 42. This is not a forecast and not evidence of an edge.

The 2014 window is run with the earnings rule off, matching Appendix A.4. The 2021 window uses earnings dates.

## 2021-01-04 → 2026-09-30

| Variant | CAGR % | Appendix | Max DD % | Sharpe | trades/yr |
|---|---:|---:|---:|---:|---:|
| SPY buy-and-hold | 14.64 | 15.07 | −24.46 | 0.93 | – |
| SPUS buy-and-hold | 17.24 | 17.61 | −28.22 | 0.95 | – |
| A | −9.93 | 3.40 | −49.45 | −0.73 | 91.5 |
| B | 3.06 | 6.80 | −31.41 | 0.32 | 69.7 |
| C / M | 8.04 | 7.71 | −24.00 | 0.65 | 79.8 |
| D2 | 9.67 | 11.93 | −27.80 | 0.71 | 64.2 |
| I | 13.68 | 13.90 | −22.91 | 0.93 | 79.3 |
| J | 2.80 | 2.98 | −21.49 | 0.29 | 63.5 |
| K | 15.51 | 9.44 | −22.94 | 0.98 | 73.6 |
| L | 1.35 | 4.46 | −28.34 | 0.17 | 60.5 |
| H | 6.51 | 7.47 | −28.18 | 0.51 | 61.9 |
| E | 2.91 | 5.78 | −18.63 | 0.28 | 73.9 |
| G | 9.92 | 7.20 | −29.32 | 0.69 | 78.8 |
| I market-on-open | 13.68 | – | −22.91 | 0.93 | 79.3 |
| I with 1×ATR cap | 11.68 | – | −23.72 | 0.83 | 80.2 |

## 2014-06-02 → 2026-09-30

| Variant | CAGR % | Appendix | Max DD % | Sharpe |
|---|---:|---:|---:|---:|
| SPY buy-and-hold | 13.69 | 13.73 | −33.71 | 0.83 |
| A | 5.86 | 11.70 | −30.20 | 0.50 |
| D2 | 13.14 | 13.50 | −28.52 | 0.91 |
| I | 14.34 | 17.88 | −25.50 | 0.98 |
| J | 5.18 | 8.54 | −23.14 | 0.49 |
| K | 14.70 | 16.78 | −26.03 | 0.92 |
| L | 4.95 | 12.96 | −31.11 | 0.44 |
| M | 9.27 | 12.04 | −19.23 | 0.71 |
| H | 11.24 | 7.05 | −33.03 | 0.80 |

## Orderings the design uses

On the 2021 window: D2 > J, I > D2, D2 > M, C > E, D2 > H. On the 2014 window: D2 > J, I > D2, D2 > M, D2 > H. C and E are the same book when the earnings rule is off.

Not every CAGR is within 2 points of Appendix A. The misses are A, B, D2 (by 2.3 points), K, L, E, and G in 2021, and A, I, J, K, L, M, and H in 2014. SPY, SPUS, C, I, J, and H in 2021, and SPY and D2 in 2014, land inside that band. Trade counts for I, D2, and J in 2021 are within about one trade per year of the appendix. No parameter was searched to close the gaps. Seed 42 is fixed for the random books.
