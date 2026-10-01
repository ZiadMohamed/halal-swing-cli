"""Stdlib JSON GET. Redirects are refused so a vendor key is not forwarded."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from swing.data.errors import VendorError

_SECRET_PARAMS = frozenset({"apikey", "api_key", "token"})


def strip_secrets(url: str) -> str:
    parts = urlsplit(url)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in _SECRET_PARAMS
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def redact(text: str, secret: str) -> str:
    cleaned = text.replace(secret, "[redacted]") if secret else text
    return cleaned[:300]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def get_json(url: str, headers: Mapping[str, str], *, timeout: float = 20.0) -> Any:
    request = urllib.request.Request(
        strip_secrets(url),
        headers={"User-Agent": "halal-swing-cli/0.1", "Accept": "application/json", **headers},
        method="GET",
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.reason if isinstance(exc.reason, str) else ""
        exc.close()
        raise VendorError(f"http_{exc.code}:{detail}") from None
    except Exception as exc:  # noqa: BLE001 — vendor boundary
        raise VendorError(f"{type(exc).__name__}:{exc}") from None
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VendorError("invalid_json") from exc
