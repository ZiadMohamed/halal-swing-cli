"""Stdlib JSON GET. Redirects are refused so a vendor key is not forwarded."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from swing.data.errors import VendorError, classify_status

_SECRET_PARAMS = frozenset({"apikey", "api_key", "token"})
_SNIPPET = 200
_BODY_READ = 4096


def strip_secrets(url: str) -> str:
    parts = urlsplit(url)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in _SECRET_PARAMS
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def redact(text: str, secret: str) -> str:
    return redact_all(text, (secret,))[:300]


def redact_all(text: str, secrets: Iterable[str]) -> str:
    cleaned = text
    for secret in secrets:
        if secret and len(secret) >= 4:
            cleaned = cleaned.replace(secret, "[redacted]")
    return cleaned


def endpoint_of(url: str) -> str:
    return urlsplit(url).path or "/"


def _header_secrets(headers: Mapping[str, str]) -> list[str]:
    found: list[str] = []
    for value in headers.values():
        found.append(value)
        if value.lower().startswith("bearer "):
            found.append(value[7:])
    return found


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def get_json(url: str, headers: Mapping[str, str], *, timeout: float = 20.0) -> Any:
    clean_url = strip_secrets(url)
    endpoint = endpoint_of(clean_url)
    secrets = _header_secrets(headers)
    request = urllib.request.Request(
        clean_url,
        headers={"User-Agent": "halal-swing-cli/0.1", "Accept": "application/json", **headers},
        method="GET",
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(_BODY_READ).decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001 — the body is diagnostic only
            body = ""
        finally:
            exc.close()
        reason = exc.reason if isinstance(exc.reason, str) else ""
        snippet = redact_all(_error_text(body) or reason, secrets)[:_SNIPPET]
        raise VendorError(snippet, kind=classify_status(exc.code), endpoint=endpoint, status=exc.code) from None
    except Exception as exc:  # noqa: BLE001 — vendor boundary
        detail = redact_all(f"{type(exc).__name__}:{exc}", secrets)[:_SNIPPET]
        raise VendorError(detail, kind="upstream", endpoint=endpoint) from None
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise VendorError("invalid_json", kind="bad_payload", endpoint=endpoint) from None


def _error_text(body: str) -> str:
    """Prefer the vendor's own `error` or `message` field over raw HTML or JSON."""
    text = body.strip()
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return text
    if isinstance(parsed, dict):
        for key in ("error", "message", "detail"):
            value = parsed.get(key)
            if isinstance(value, str) and value:
                return value
    return text
