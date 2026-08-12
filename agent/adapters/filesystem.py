"""FileSystemSubstrateAdapter — honest probe against committed parquets.

This is the only adapter implemented in this PR. It reads a panel
from disk, passes it through feed_sentinel + schema_auditor, and
exposes the subset of the §8 API contract that does NOT require a
live provider. Write actions (collect, backfill, enrich) raise
``NotImplementedError`` because they can only be honoured by a real
vendor — the agent routes them back through the provider registry.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from agent.models import (
    AssetSchemaReport,
    SourceDescriptor,
    SubstrateHealth,
)
from agent.modules.feed_sentinel import compute_health
from agent.modules.schema_auditor import audit_panel
from agent.providers import all_sources


class FileSystemSubstrateAdapter:
    """Deterministic probe: reads a parquet, computes health + schema.

    The adapter is stateless — every call re-reads the file so drift
    is caught without needing a daemon process. Works for exactly the
    shape of panel we have on disk (index=``ts``, columns=asset names).
    """

    def __init__(self, panel_path: Path) -> None:
        self.panel_path = Path(panel_path)

    # ------- §8 API contract (read-side) ------- #

    def get_sources(self) -> list[SourceDescriptor]:
        """Return the full provider registry (configured or not)."""
        return all_sources()

    def get_health(self, wall_clock_now: datetime | None = None) -> SubstrateHealth:
        panel = self._load_panel()
        return compute_health(panel, wall_clock_now=wall_clock_now)

    def get_schema(self) -> list[AssetSchemaReport]:
        panel = self._load_panel()
        return audit_panel([str(c) for c in panel.columns])

    # ------- §8 API contract (write-side — intentionally fail-closed) ------- #

    def collect(self, **_: object) -> None:
        raise NotImplementedError(
            "FileSystemSubstrateAdapter has no vendor — "
            "agent must route COLLECT via a real MicrostructureProvider "
            "(see agent/providers.py)."
        )

    def backfill(self, **_: object) -> None:
        raise NotImplementedError(
            "backfill requires a live vendor adapter; route via provider registry."
        )

    def enrich(self, **_: object) -> None:
        raise NotImplementedError(
            "enrich cannot synthesise bid/ask from OHLC closes; substrate upgrade required first."
        )

    # ------- Internal ------- #

    def _load_panel(self) -> pd.DataFrame:
        if not self.panel_path.exists():
            return pd.DataFrame()
        df = pd.read_parquet(self.panel_path)
        df.index = pd.to_datetime(df.index)
        return df.sort_index()


__all__ = ["FileSystemSubstrateAdapter"]
