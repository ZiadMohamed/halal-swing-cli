"""Advisory research records. They are not checklist inputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ResearchHit:
    title: str
    url: str
    snippet: str


@dataclass(frozen=True)
class ResearchResult:
    status: Literal["ok", "skipped", "error"]
    provider: str
    reason: str | None
    query: str | None
    hits: tuple[ResearchHit, ...] = ()
    advisory_only: bool = True
    affects_checklist_math: bool = False

    def __post_init__(self) -> None:
        if self.affects_checklist_math:
            raise ValueError("research cannot affect checklist math")
        if self.advisory_only is not True:
            raise ValueError("research is advisory only")
