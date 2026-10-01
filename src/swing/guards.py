"""Product locks that sit in front of the checklist."""

from __future__ import annotations

from swing.codes import ReasonCode


def product_block(
    side: str,
    instrument: str,
    account_mode: str,
    longs_only: bool = True,
) -> ReasonCode | None:
    """Return a block code, or None when the intent is long cash equity.

    Anything other than side long, instrument equity, and a cash account blocks.
    There is no combined "trade anyway" path.
    """
    if not longs_only or side != "long":
        return ReasonCode.BLOCK_SHORT
    if instrument != "equity":
        return ReasonCode.BLOCK_DERIVATIVE
    if account_mode != "cash":
        return ReasonCode.BLOCK_MARGIN
    return None
