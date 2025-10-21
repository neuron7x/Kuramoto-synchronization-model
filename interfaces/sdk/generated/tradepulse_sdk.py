"""High-level SDK entrypoint."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class TradePulseSDK:
    components: dict[str, Any]

    @classmethod
    def from_components(cls, **components: Any) -> "TradePulseSDK":
        return cls(components=components)

    def get(self, name: str) -> Any:
        return self.components[name]


__all__ = ["TradePulseSDK"]
