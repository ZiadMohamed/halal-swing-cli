"""Stable config hash. Do not change the encoding without a version bump."""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel


def config_hash(config: BaseModel) -> str:
    """SHA-256 of canonical JSON for a Pydantic model.

    Encoding is part of the product contract: UTF-8, sorted keys, compact
    separators, ASCII escapes. Paths, secrets, and live headlines are not
    fields on the hashed model.
    """
    payload = config.model_dump(mode="json")
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
