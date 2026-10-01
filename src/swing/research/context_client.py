"""Context.dev web search for runtime stock checks.

OHLC does not come from this client. A missing key never reaches this class;
the factory returns NullResearch instead.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from swing.research.models import ResearchHit, ResearchResult

_DEFAULT_BASE = "https://api.context.dev/v1"
_Opener = Callable[..., Any]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Do not forward the bearer token to another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def _default_opener(req: urllib.request.Request, timeout: float = 8.0) -> Any:
    opener = urllib.request.build_opener(_NoRedirect)
    return opener.open(req, timeout=timeout)


def _redact(text: str, secret: str) -> str:
    cleaned = text.replace(secret, "[redacted]") if secret else text
    return cleaned[:300]


class ContextLiveResearch:
    def __init__(
        self,
        api_key: str,
        base_url: str = _DEFAULT_BASE,
        timeout_s: float = 8.0,
        opener: _Opener | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._opener = opener or _default_opener

    def enrich(self, ticker: str) -> ResearchResult:
        query = f"{ticker} stock news"
        url = f"{self._base_url}/web/search"
        body = {
            "query": query,
            "numResults": 10,
            "freshness": "last_week",
            "country": "us",
            "timeoutMS": int(self._timeout_s * 1000),
        }
        raw_body = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=raw_body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "halal-swing-cli/0.1",
            },
            method="POST",
        )
        try:
            with self._opener(request, timeout=self._timeout_s) as response:
                payload_bytes = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.reason if isinstance(exc.reason, str) else ""
            reason = _redact(f"http_{exc.code}:{detail}", self._api_key)
            exc.close()
            return self._error(query, reason)
        except Exception as exc:  # noqa: BLE001 — fail-soft boundary
            return self._error(query, _redact(f"{type(exc).__name__}:{exc}", self._api_key))
        try:
            payload = json.loads(payload_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._error(query, "invalid_json")
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            return self._error(query, "invalid_payload")
        hits = _hits(payload)
        return ResearchResult(
            status="ok",
            provider="context",
            reason=None,
            query=query,
            hits=hits,
        )

    def _error(self, query: str, reason: str) -> ResearchResult:
        return ResearchResult(
            status="error",
            provider="context",
            reason=reason,
            query=query,
            hits=(),
        )


def _hits(payload: object) -> tuple[ResearchHit, ...]:
    if not isinstance(payload, dict):
        return ()
    rows = payload.get("results")
    if not isinstance(rows, list):
        return ()
    collected: list[ResearchHit] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = row.get("title")
        url = row.get("url")
        snippet = row.get("description") or ""
        if not isinstance(title, str) or not isinstance(url, str):
            continue
        if not isinstance(snippet, str):
            snippet = ""
        collected.append(ResearchHit(title=title, url=url, snippet=snippet))
    return tuple(collected)
