"""Paper journal stub. Chat 5 appends JSONL. Nothing is written here."""

from __future__ import annotations


class PaperJournal:
    def append(self, envelope: object) -> None:
        raise NotImplementedError(
            "Paper JSONL journal is not installed in the skeleton. "
            "Chat 5 (hardening) appends planned entries."
        )
