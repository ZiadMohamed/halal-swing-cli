"""Gate order from the frozen checklist. Chat 3 fills these in."""

from __future__ import annotations

PIPELINE_GATES: tuple[str, ...] = (
    "data_auth",
    "liquidity",
    "soft_veto",
    "earnings",
    "regime",
    "heat",
    "setup_mutex",
    "rr_stop",
    "next_open",
)
