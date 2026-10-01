"""Context live search is advisory and fail-soft."""

import json
import urllib.error

from swing.config import SwingConfig
from swing.research.context_client import ContextLiveResearch
from swing.research.factory import build_live_research
from swing.research.models import ResearchHit


class _Resp:
    def __init__(self, payload: bytes, status: int = 200):
        self._payload = payload
        self.status = status

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_missing_key_skips(monkeypatch):
    monkeypatch.delenv("CONTEXT_DEV_API_KEY", raising=False)
    client = build_live_research(SwingConfig(), env={})
    result = client.enrich("AAPL")
    assert result.status == "skipped"
    assert result.reason == "missing_api_key"
    assert result.advisory_only is True
    assert result.affects_checklist_math is False
    assert result.hits == ()


def test_disabled_config_skips_even_with_a_key():
    cfg = SwingConfig.model_validate({"research": {"enabled": False}})
    client = build_live_research(cfg, env={"CONTEXT_DEV_API_KEY": "ctxt_test"})
    result = client.enrich("AAPL")
    assert result.status == "skipped"
    assert result.reason == "disabled"


def test_factory_builds_context_client_when_keyed():
    client = build_live_research(
        SwingConfig(),
        env={"CONTEXT_DEV_API_KEY": "ctxt_test", "CONTEXT_DEV_BASE_URL": "https://example.test/v1"},
    )
    assert isinstance(client, ContextLiveResearch)


def test_context_search_sends_bearer_header_and_parses_hits():
    seen = {}

    def opener(req, timeout=0):
        seen["url"] = req.full_url
        seen["auth"] = req.get_header("Authorization")
        seen["body"] = json.loads(req.data.decode())
        seen["timeout"] = timeout
        payload = {
            "query": "AAPL stock news",
            "results": [
                {
                    "url": "https://example.com/aapl",
                    "title": "AAPL headline",
                    "description": "A calendar item, not a price.",
                }
            ],
        }
        return _Resp(json.dumps(payload).encode())

    client = ContextLiveResearch(api_key="ctxt_secret", base_url="https://api.context.dev/v1", opener=opener)
    result = client.enrich("AAPL")
    assert seen["url"] == "https://api.context.dev/v1/web/search"
    assert seen["auth"] == "Bearer ctxt_secret"
    assert "api_key" not in seen["url"]
    assert seen["body"]["query"] == "AAPL stock news"
    assert seen["body"]["numResults"] == 10
    assert "ctxt_secret" not in json.dumps(seen["body"])
    assert result.status == "ok"
    assert result.provider == "context"
    assert result.hits == (
        ResearchHit(
            title="AAPL headline",
            url="https://example.com/aapl",
            snippet="A calendar item, not a price.",
        ),
    )
    assert result.affects_checklist_math is False


def test_insecure_base_url_does_not_send_the_key():
    client = build_live_research(
        SwingConfig(),
        env={"CONTEXT_DEV_API_KEY": "ctxt_secret", "CONTEXT_DEV_BASE_URL": "http://evil.example/v1"},
    )
    assert not isinstance(client, ContextLiveResearch)
    result = client.enrich("AAPL")
    assert result.status == "error"
    assert result.reason == "insecure_base_url"
    assert result.hits == ()
    assert "ctxt_secret" not in (result.reason or "")


def test_https_base_url_builds_the_context_client():
    client = build_live_research(
        SwingConfig(),
        env={"CONTEXT_DEV_API_KEY": "ctxt_test", "CONTEXT_DEV_BASE_URL": "https://api.context.dev/v1"},
    )
    assert isinstance(client, ContextLiveResearch)


def test_missing_results_array_is_an_error():
    def opener(req, timeout=0):
        return _Resp(b'{"query": "AAPL stock news"}')

    client = ContextLiveResearch(api_key="ctxt_secret", opener=opener)
    result = client.enrich("AAPL")
    assert result.status == "error"
    assert result.reason == "invalid_payload"
    assert "ctxt_secret" not in (result.reason or "")


def test_http_error_is_soft_and_redacts_the_key():
    def opener(req, timeout=0):
        raise urllib.error.HTTPError(
            req.full_url,
            401,
            "invalid ctxt_secret",
            hdrs=None,
            fp=None,
        )

    client = ContextLiveResearch(api_key="ctxt_secret", opener=opener)
    result = client.enrich("MSFT")
    assert result.status == "error"
    assert result.hits == ()
    blob = json.dumps(
        {
            "reason": result.reason,
            "query": result.query,
        }
    )
    assert "ctxt_secret" not in blob
    assert result.advisory_only is True
