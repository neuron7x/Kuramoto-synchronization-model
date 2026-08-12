"""Deterministic main loop §15 of SYSTEM_ARTIFACT_v9.0.

Single-pass entry point. Given a substrate adapter, run one tick of
the state machine and return the emitted ``ActionIntent``. The loop
is deterministic (no wall-clock jitter beyond the health snapshot),
so replay-hashes are stable across runs on identical inputs.

Call directly::

    python -m agent.main
    python -m agent.main --panel data/askar_full/panel_hourly.parquet

The default panel is ``data/askar_full/panel_hourly.parquet``. On the
committed OHLC substrate the agent immediately emits
``DISCOVER_SOURCES`` with ``substrate_status=DEAD`` because INV_001
forbids precursor claims from close-only inputs.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from agent.adapters.filesystem import FileSystemSubstrateAdapter
from agent.models import ActionIntent
from agent.modules.reporter import emit_replay_hash, write_report
from agent.policy import select_action
from agent.providers import provider_manifest

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PANEL = REPO_ROOT / "data" / "askar_full" / "panel_hourly.parquet"


def run_once(
    panel_path: Path | None = None,
    wall_clock_now: datetime | None = None,
) -> ActionIntent:
    """Execute one deterministic pass over the agent pipeline."""
    panel = panel_path or DEFAULT_PANEL
    adapter = FileSystemSubstrateAdapter(panel)

    now = wall_clock_now or datetime.now(tz=timezone.utc)
    sources = adapter.get_sources()
    health = adapter.get_health(wall_clock_now=now)
    schemas = adapter.get_schema()

    intent = select_action(
        sources=sources,
        health=health,
        schemas=schemas,
        verdict=None,
        missing_artifacts=[],
    )

    # Persist audit artefacts.
    write_report(
        "provider_manifest.json",
        provider_manifest(),
    )
    write_report(
        "substrate_health.json",
        health.to_dict(),
    )
    write_report(
        "schema_audit.json",
        {"assets": [s.to_dict() for s in schemas]},
    )
    payload = intent.to_dict()
    write_report("action_intent.json", payload)
    emit_replay_hash(payload)
    return intent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--panel",
        type=Path,
        default=DEFAULT_PANEL,
        help="Path to a parquet panel (default: data/askar_full/panel_hourly.parquet)",
    )
    args = parser.parse_args(argv)

    try:
        intent = run_once(panel_path=args.panel)
    except FileNotFoundError as exc:
        print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
        return 2

    print(json.dumps(intent.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
