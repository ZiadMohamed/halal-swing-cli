"""Open risk the heat gate reads. The paper journal does not fill this yet."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OpenPosition:
    """One open long. `risk_fraction` is the fraction of equity at risk, not shares.

    `sector` is caller-supplied. v0 has no sector vendor. A missing sector does
    not join an "unknown" bucket.
    """

    ticker: str
    risk_fraction: float
    sector: str | None = None
