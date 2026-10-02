# ADR 0002 — Redesign of the daily book

Date: 2026-10-02
Status: accepted
Supersedes: the v0 prefs table in ADR 0001 for product shape. ADR 0001 still records the Python and uv choice.

## Context

The v0 tool checked one ticker, appended every plan to a journal, called a premium Finnhub dividend endpoint, and had no way to compare a rule to a buy-and-hold of SPUS. The redesign plan in `docs/REDESIGN_PLAN.md` is the spec. Capital protection stays in the code. Ease of setup is last.

## Decision

- Home is `~/.swing`. The old macOS folder is copied once and not deleted.
- Bars come from Massive grouped daily, with a throttled backfill and yfinance behind that. Finnhub is earnings only.
- Fills live in `book.jsonl`. Plans live in `plans.jsonl`. The v0 journal is archived and imported as plans, not as fills.
- `swing backtest` runs the Appendix A variants and the measured v1 book on cached bars. There is no parameter search.
- The live checklist stays on v0. v1 beat v0 on CAGR and Sharpe in both windows and beat random rank on CAGR, but in the 2014 window the random-rank Sharpe was higher (0.95 vs 0.90). That failed the ship rule. The tables are in `docs/backtests/`.

## Consequences

- `swing analyze` still uses the mutex, the 2R target, and the heat caps.
- `exit.mode`, `regime.gate`, slot count, liquidity floors, and the entry cap exist as backtest variant fields. They are not yet the live config, because v1 was not shipped.
- A later change to the live book needs a new harness run, not a grid search.
- The CLI still does not send orders.

Not financial advice. Not a Shariah certification.
