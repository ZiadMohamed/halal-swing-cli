"""Append-only paper journal. One JSON object per planned ENTER_LONG."""

from __future__ import annotations

import json
import math
from pathlib import Path

from swing.brain.positions import OpenPosition
from swing.codes import DecisionKind
from swing.envelope import Envelope
from swing.paths import journal_path


class PaperJournal:
    """JSONL book of planned longs. Lines are appended and never rewritten."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = journal_path() if path is None else Path(path)

    def append(
        self,
        envelope: Envelope,
        *,
        equity_usd: float | None,
        sector: str | None = None,
    ) -> None:
        """Append one line when the envelope is ENTER_LONG.

        `NO_TRADE` and `BLOCK` leave the file untouched, including not creating it.
        `risk_fraction` is `size_shares * (entry - stop) / equity_usd`. Share
        count is copied from the plan. Equity is never invented.
        """
        if envelope.decision is not DecisionKind.ENTER_LONG or envelope.plan is None:
            return
        equity = _equity(equity_usd)
        plan = envelope.plan
        risk = plan.size_shares * (plan.entry - plan.stop) / equity
        if not math.isfinite(risk) or risk <= 0:
            raise ValueError("risk fraction is not positive. The journal line was not written.")
        record = {
            "schema_version": "1",
            "ticker": envelope.ticker,
            "decision": envelope.decision.value,
            "side": envelope.side,
            "setup": plan.setup,
            "entry": plan.entry,
            "stop": plan.stop,
            "target": plan.target,
            "size_shares": plan.size_shares,
            "next_open": plan.next_open,
            "risk_fraction": risk,
            "equity_usd": equity,
            "sector": _clean_sector(sector),
            "config_hash": envelope.config_hash,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, sort_keys=True, ensure_ascii=False)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def load_positions(self) -> tuple[OpenPosition, ...]:
        """Read every planned line as open risk. A bad line refuses the book."""
        if not self.path.is_file():
            return ()
        positions: list[OpenPosition] = []
        for index, raw in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
            if not raw.strip():
                continue
            positions.append(_position(index, raw))
        return tuple(positions)


def _equity(equity_usd: float | None) -> float:
    if isinstance(equity_usd, bool) or not isinstance(equity_usd, (int, float)):
        raise ValueError("account.equity_usd is unset. No risk fraction was invented.")
    equity = float(equity_usd)
    if not math.isfinite(equity) or equity <= 0:
        raise ValueError("account.equity_usd is unset. No risk fraction was invented.")
    return equity


def _clean_sector(sector: str | None) -> str | None:
    if sector is None:
        return None
    text = sector.strip()
    return text or None


def _position(index: int, raw: str) -> OpenPosition:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"journal line {index} is not JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"journal line {index} is not an object")
    if payload.get("decision") != DecisionKind.ENTER_LONG.value:
        raise ValueError(f"journal line {index} is not an ENTER_LONG plan")
    ticker = payload.get("ticker")
    if not isinstance(ticker, str) or not ticker.strip():
        raise ValueError(f"journal line {index} is missing ticker")
    if "risk_fraction" not in payload:
        raise ValueError(f"journal line {index} is missing risk_fraction")
    risk = payload["risk_fraction"]
    if isinstance(risk, bool) or not isinstance(risk, (int, float)) or not math.isfinite(float(risk)):
        raise ValueError(f"journal line {index} risk_fraction is not a finite number")
    sector = payload.get("sector")
    if sector is not None and not isinstance(sector, str):
        raise ValueError(f"journal line {index} sector is not a string")
    return OpenPosition(
        ticker=ticker.strip(),
        risk_fraction=float(risk),
        sector=_clean_sector(sector if isinstance(sector, str) else None),
    )
