"""Feed Sentinel (§4.B): liveness + freshness + NaN policy + quality score.

Computes a ``SubstrateHealth`` snapshot from a materialised panel. On
the current committed substrate (no live feed), "freshness" is the
age of the parquet file's last data bar relative to ``wall_clock_now``,
not the file mtime — a panel that was built years ago but contains
fresh data would still be stale, and a panel that was rebuilt today
from ancient data should also register as stale. The physics is the
age of the *content*, not the file.

Empty / missing panels report ``freshness_minutes = DEAD_FRESHNESS_SENTINEL``
(100 years in minutes) — a large finite number that round-trips through
RFC-compliant JSON. Using ``float("inf")`` here would emit ``Infinity``
into the audit artefacts and break non-Python consumers in CI/ops.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from agent.models import SubstrateHealth, SubstrateLabel, SubstrateStatus
from agent.modules.schema_auditor import audit_panel, is_ohlc_close_only

#: Large finite sentinel for "no data / definitely dead" — JSON-safe
#: replacement for ``float("inf")``. 100 years in minutes ≈ 5.26e7.
DEAD_FRESHNESS_SENTINEL: float = 100.0 * 365.0 * 24.0 * 60.0

#: Anything older than 30 days is treated as DEAD regardless of schema.
DEAD_AGE_MINUTES: float = 30.0 * 24.0 * 60.0


def compute_health(
    panel: pd.DataFrame,
    wall_clock_now: datetime | None = None,
) -> SubstrateHealth:
    now = wall_clock_now or datetime.now(tz=timezone.utc)

    # --- freshness ---
    # Empty panel → DEAD_FRESHNESS_SENTINEL, NOT float('inf'). Infinity
    # is not RFC-compliant JSON and would corrupt every downstream
    # audit artefact (the CodeRabbit P2 fix).
    if len(panel) == 0:
        freshness_minutes = DEAD_FRESHNESS_SENTINEL
        last_ts = None
    else:
        idx = pd.DatetimeIndex(panel.index)
        last_ts_ts = idx.max()
        last_ts = (
            last_ts_ts.to_pydatetime().replace(tzinfo=timezone.utc)
            if last_ts_ts.tzinfo is None
            else last_ts_ts.to_pydatetime()
        )
        delta = now - last_ts
        freshness_minutes = float(delta.total_seconds() / 60.0)
        if freshness_minutes < 0:
            freshness_minutes = 0.0

    # --- NaN rate (strict policy: any NaN > 0 is a violation) ---
    total_cells = max(1, panel.size)
    nan_cells = int(panel.isna().sum().sum())
    nan_rate = float(nan_cells / total_cells)

    # --- duplicate timestamps ---
    n_bars = int(len(panel))
    if n_bars > 0:
        dup_cells = int(panel.index.duplicated().sum())
        duplicate_rate = float(dup_cells / n_bars)
    else:
        duplicate_rate = 0.0

    # --- asset coverage ---
    asset_coverage = int(panel.shape[1])

    # --- gap count: count daily-scale gaps > 5 days in the index ---
    gap_count = 0
    if n_bars >= 2:
        idx = pd.DatetimeIndex(panel.index)
        diffs = idx.to_series().diff().dropna()
        gap_count = int((diffs > pd.Timedelta(days=5)).sum())

    # --- schema audit ---
    schemas = audit_panel(list(map(str, panel.columns)))
    precursor_capable_assets = int(sum(1 for s in schemas if s.precursor_capable))
    schema_complete = precursor_capable_assets > 0
    substrate_label = (
        SubstrateLabel.LATE_GEOMETRY_ONLY if is_ohlc_close_only(schemas) else SubstrateLabel.LIVE
    )

    # --- quality score in [0, 1] — heuristic composition ---
    quality = 0.0
    if n_bars > 0:
        quality = (
            (1.0 if n_bars >= 1000 else n_bars / 1000.0) * 0.2
            + (0.0 if nan_rate > 0 else 0.2)
            + (0.2 if duplicate_rate == 0 else 0.0)
            + (0.2 if gap_count == 0 else 0.0)
            + (0.2 if schema_complete else 0.0)
        )
    quality_score = max(0.0, min(1.0, quality))

    # --- status ---
    if not schema_complete:
        status = SubstrateStatus.DEGRADED
    elif quality_score < 0.6:
        status = SubstrateStatus.DEGRADED
    else:
        status = SubstrateStatus.LIVE

    # Freshness override: any panel older than 30 days → DEAD regardless of
    # schema. Sentinel-old empty panels (100 years) trip this trivially.
    if not np.isfinite(freshness_minutes) or freshness_minutes > DEAD_AGE_MINUTES:
        status = SubstrateStatus.DEAD

    feed_live = status != SubstrateStatus.DEAD
    heartbeat_ok = status != SubstrateStatus.DEAD

    return SubstrateHealth(
        ts=now,
        status=status,
        feed_live=feed_live,
        heartbeat_ok=heartbeat_ok,
        freshness_minutes=freshness_minutes,
        asset_coverage=asset_coverage,
        gap_count=gap_count,
        nan_rate=nan_rate,
        duplicate_rate=duplicate_rate,
        schema_complete=schema_complete,
        precursor_capable_assets=precursor_capable_assets,
        quality_score=quality_score,
        substrate_label=substrate_label,
    )


__all__ = ["compute_health"]
