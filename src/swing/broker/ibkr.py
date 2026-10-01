"""IBKR adapter stub. No network. No orders."""

from __future__ import annotations


class IbkrBrokerStub:
    def place_order(self, plan: object) -> None:
        raise NotImplementedError(
            "IBKR live trading is out of scope for v0. "
            "Paper JSONL is the only journal, and it is not wired yet."
        )
