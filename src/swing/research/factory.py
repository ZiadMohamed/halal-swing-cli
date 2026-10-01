"""Pick a live-research client from config and the environment."""

from __future__ import annotations

import os
from collections.abc import Mapping

from swing.config import SwingConfig
from swing.research.context_client import ContextLiveResearch
from swing.research.null import NullResearch

_DEFAULT_BASE = "https://api.context.dev/v1"


def build_live_research(config: SwingConfig, env: Mapping[str, str] | None = None) -> NullResearch | ContextLiveResearch:
    environ = os.environ if env is None else env
    if not config.research.enabled:
        return NullResearch("disabled")
    key = environ.get("CONTEXT_DEV_API_KEY", "").strip()
    if not key:
        return NullResearch("missing_api_key")
    base = environ.get("CONTEXT_DEV_BASE_URL", _DEFAULT_BASE).strip() or _DEFAULT_BASE
    return ContextLiveResearch(api_key=key, base_url=base)
