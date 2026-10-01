# ADR 0001 — Python + uv, and the data / brain / output split

Date: 2026-10-01
Status: accepted (Chat 1)

## Context

Personal local CLI for Ziad Osman on macOS (Apple Silicon and Intel). A ticker goes in. A deterministic swing checklist comes out: entry, stop, target, size, next NYSE open, and decision codes. Cash longs only. The user supplies pre-screened halal tickers. v0 does not call Zoya and does not issue a Shariah ruling.

Research (round 10) recommended Python + uv and Parquet bars. This ADR confirms that stack. It is not an override.

## Decision

Use Python 3.12 and uv. Ship one installable console script, `swing`. Validate config with Pydantic. Store user config as TOML. Stamp a SHA-256 of the canonical config JSON on every envelope.

Split the process into four areas that do not share mutable state:

| Area | Owns | Must not own |
|---|---|---|
| Data (Chat 2) | Bars, events, calendar, Parquet cache | Setup rules, order placement |
| Brain (Chat 3) | Gates, indicators, setups, mutex, size, heat | HTTP clients, terminal layout |
| Output (Chat 4) | Envelope rendering, `--json`, `--compact`, Cairo/New York next-open text | Indicator math |
| Hardening (Chat 5) | Fixtures, paper JSONL journal, IBKR stub remains unwired | Live orders |

Live web search sits beside the brain, not inside it. Context.dev (`POST /web/search`) is the default provider. It enriches the envelope with advisory headlines. It is not an OHLC vendor. Finnhub, when Chat 2 adds it, is events and calendars only.

## Why this stack

- yfinance (prototype bars) and PyArrow (Parquet) are Python libraries. The checklist math is array math on daily bars, which Python already does well.
- uv installs a pinned CPython on both Apple Silicon and Intel Macs, writes `uv.lock`, and does not require a system Python.
- A Go or Rust binary would be a nicer single file and a worse data stack. Rebuilding yfinance, Parquet, and the indicator code in a second language is cost without a product gain for a personal CLI.
- Node would add a runtime Ziad does not need for a terminal tool and has a weaker daily-bar story.

## Consequences

- macOS is the documented install path. Linux is a fallback for CI and this cloud agent, and path code says so.
- Chat 2 added `yfinance`, `pyarrow`, and `exchange-calendars`. Massive and Finnhub use the stdlib HTTP client.
- Config hash changes if a later chat changes a hashed field. New policy belongs in `SwingConfig` on purpose, not in ad-hoc constants.
- `research.affects_checklist_math` is fixed `false`. News text cannot move entry, stop, target, size, or next_open.
