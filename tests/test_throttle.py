"""Massive calls stay at or under five per minute."""

from swing.data.throttle import RateLimiter


def test_limiter_spaces_calls_on_a_fake_clock():
    clock = {"t": 0.0}
    slept: list[float] = []

    def now() -> float:
        return clock["t"]

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        clock["t"] += seconds

    limiter = RateLimiter(5, now=now, sleep=sleep)
    stamps: list[float] = []
    for _ in range(6):
        limiter.acquire()
        stamps.append(clock["t"])
    assert slept == [12.0, 12.0, 12.0, 12.0, 12.0]
    assert stamps == [0.0, 12.0, 24.0, 36.0, 48.0, 60.0]
    gaps = [right - left for left, right in zip(stamps, stamps[1:])]
    assert min(gaps) >= 12.0
