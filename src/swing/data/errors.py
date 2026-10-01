"""Typed data-layer errors. Missing vendor keys use these, not a crash."""

from __future__ import annotations


class DataError(Exception):
    """Base error for bars, events, and the NYSE calendar."""

    code = "data_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class MissingApiKeyError(DataError):
    """A required vendor key is absent. Import and --help do not raise this."""

    def __init__(self, env_name: str) -> None:
        self.env_name = env_name
        super().__init__(f"{env_name} is not set", code="missing_api_key")


class VendorError(DataError):
    """The vendor answered, but the payload is unusable. The key is not included."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="vendor_error")
