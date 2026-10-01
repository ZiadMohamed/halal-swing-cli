"""Text and JSON views. Compact is opt-in. The disclaimer stays on both."""

from __future__ import annotations

import json

from swing.envelope import Envelope


def render_json(envelope: Envelope) -> str:
    payload = envelope.model_dump(mode="json")
    return json.dumps(payload, indent=2) + "\n"


def render_text(envelope: Envelope) -> str:
    lines = [
        f"{envelope.ticker}  {envelope.decision.value}",
        f"config_hash {envelope.config_hash}",
    ]
    if envelope.reasons:
        lines.append("reasons: " + ", ".join(item.code.value for item in envelope.reasons))
    if envelope.warnings:
        lines.append("warnings: " + ", ".join(item.code.value for item in envelope.warnings))
    if envelope.research.status != "ok":
        lines.append(f"research: {envelope.research.status} ({envelope.research.reason})")
    if not envelope.compact:
        lines.append(f"stage: {envelope.stage} — data and brain not run")
        for gate in envelope.gates:
            lines.append(f"  {gate.name}: {gate.status}")
    lines.append(envelope.disclaimer)
    return "\n".join(lines) + "\n"
