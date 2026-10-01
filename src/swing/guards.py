"""Product locks that sit in front of the checklist."""

from __future__ import annotations

from swing.codes import ReasonCode

_DERIVATIVES = frozenset({"option", "cfd", "future"})


def product_block(side: str, instrument: str, account_mode: str) -> ReasonCode | None:
    """Return a block code, or None when the intent is long cash equity.

    Side is checked first, then instrument, then account. There is no
    combined "trade anyway" path.
    """
    if side != "long":
        return ReasonCode.BLOCK_SHORT
    if instrument in _DERIVATIVES:
        return ReasonCode.BLOCK_DERIVATIVE
    if account_mode != "cash":
        return ReasonCode.BLOCK_MARGIN
    return None
