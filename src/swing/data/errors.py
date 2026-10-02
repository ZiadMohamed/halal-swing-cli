"""Typed data-layer errors. Missing vendor keys use these, not a crash."""

from __future__ import annotations

ERROR_KINDS = (
    "missing_key",
    "invalid_key",
    "plan_forbidden",
    "rate_limited",
    "upstream",
    "bad_payload",
)

_FIXES = {
    "missing_key": "Set {env} in the shell or your swing .env file.",
    "invalid_key": "The key was rejected (HTTP 401). Copy it again from the vendor dashboard.",
    "plan_forbidden": "This endpoint is outside your plan (HTTP 403). The key works; the endpoint is not free.",
    "rate_limited": "The vendor rate-limited this key (HTTP 429). Wait a minute and run again.",
    "upstream": "The vendor or the network failed. Run again later.",
    "bad_payload": "The vendor answered with an unexpected response. Run again; if it repeats, check the snippet.",
}


class DataError(Exception):
    """Base error for bars, events, and the NYSE calendar."""

    code = "data_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class MissingApiKeyError(DataError):
    """A required vendor key is absent. Import and --help do not raise this."""

    kind = "missing_key"

    def __init__(self, env_name: str) -> None:
        self.env_name = env_name
        super().__init__(f"{env_name} is not set", code="missing_api_key")


class VendorError(DataError):
    """The vendor call failed. The text names the endpoint and status, never the key.

    `str(error)` reads `endpoint:http_STATUS:kind:snippet`, with absent parts left out.
    """

    def __init__(
        self,
        detail: str,
        *,
        kind: str = "bad_payload",
        endpoint: str | None = None,
        status: int | None = None,
    ) -> None:
        if kind not in ERROR_KINDS:
            raise ValueError(f"unknown vendor error kind: {kind}")
        self.detail = " ".join(detail.split())
        self.kind = kind
        self.endpoint = endpoint
        self.status = status
        parts = [part for part in (endpoint, None if status is None else f"http_{status}", kind, self.detail) if part]
        super().__init__(":".join(parts), code="vendor_error")


def classify_status(status: int) -> str:
    if status == 401:
        return "invalid_key"
    if status == 403:
        return "plan_forbidden"
    if status == 429:
        return "rate_limited"
    if status >= 500:
        return "upstream"
    return "bad_payload"


def fix_line(kind: str, env_name: str | None = None) -> str:
    template = _FIXES.get(kind, _FIXES["bad_payload"])
    return template.format(env=env_name or "the vendor key")


def kind_of(error_text: str) -> str | None:
    """Recover the error kind from a stored error string."""
    if error_text.startswith("missing_api_key:"):
        return "missing_key"
    for token in error_text.split(":"):
        if token in ERROR_KINDS:
            return token
    return None
