"""Fail-soft research used when Context is off or unconfigured."""

from __future__ import annotations

from typing import Literal

from swing.research.models import ResearchResult


class NullResearch:
    def __init__(self, reason: str, *, status: Literal["skipped", "error"] = "skipped") -> None:
        self._reason = reason
        self._status = status

    def enrich(self, ticker: str) -> ResearchResult:
        del ticker
        return ResearchResult(
            status=self._status,
            provider="none",
            reason=self._reason,
            query=None,
            hits=(),
        )
