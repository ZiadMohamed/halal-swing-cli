"""Fail-soft research used when Context is off or unconfigured."""

from __future__ import annotations

from swing.research.models import ResearchResult


class NullResearch:
    def __init__(self, reason: str) -> None:
        self._reason = reason

    def enrich(self, ticker: str) -> ResearchResult:
        del ticker
        return ResearchResult(
            status="skipped",
            provider="none",
            reason=self._reason,
            query=None,
            hits=(),
        )
