"""Space vendor calls so a free-tier limit is not crossed."""

from __future__ import annotations

import time
from collections.abc import Callable


class RateLimiter:
    """At most `per_minute` acquisitions, spaced evenly."""

    def __init__(
        self,
        per_minute: int = 5,
        *,
        now: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        if per_minute < 1:
            raise ValueError("per_minute must be positive")
        self.per_minute = per_minute
        self._gap = 60.0 / per_minute
        self._now = now or time.monotonic
        self._sleep = sleep or time.sleep
        self._last: float | None = None

    def acquire(self) -> None:
        current = self._now()
        if self._last is not None:
            wait = self._gap - (current - self._last)
            if wait > 0:
                self._sleep(wait)
                current = self._now()
        self._last = current
