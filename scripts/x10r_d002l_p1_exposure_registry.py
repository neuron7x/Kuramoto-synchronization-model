#!/usr/bin/env python3
"""CLI for D-002L-P1 official Treasury exposure-registry construction."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from research.systemic_risk.d002l_exposure_registry import (
    D002LExposureError,
    blocked_result,
    compile_registry,
    fetch_official_snapshot,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fetch-official", action="store_true")
    mode.add_argument("--raw", type=Path)
    ap.add_argument("--provenance", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--raw-out", type=Path)
    ap.add_argument("--provenance-out", type=Path)
    ap.add_argument("--status-out", type=Path)
    ap.add_argument("--timeout-seconds", type=int, default=30)
    ns = ap.parse_args()

    attempt = {
        "executed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "mode": "fetch_official" if ns.fetch_official else "provided_raw",
    }
    try:
        if ns.fetch_official:
            raw, provenance = fetch_official_snapshot(timeout_seconds=ns.timeout_seconds)
            if ns.raw_out:
                ns.raw_out.parent.mkdir(parents=True, exist_ok=True)
                ns.raw_out.write_bytes(raw)
            if ns.provenance_out:
                _write_json(ns.provenance_out, provenance)
            hint = "html"
        else:
            if ns.provenance is None:
                raise D002LExposureError("--provenance is required with --raw")
            raw = ns.raw.read_bytes()
            provenance = json.loads(ns.provenance.read_text(encoding="utf-8"))
            hint = ns.raw.suffix
        registry = compile_registry(raw, provenance, format_hint=hint)
        _write_json(ns.out, registry)
        if ns.status_out:
            direct_fetch = bool(ns.fetch_official)
            _write_json(
                ns.status_out,
                {
                    "schema_version": "D002L-P1-EXECUTION-STATUS-v1",
                    "study_id": "D-002L",
                    "node_id": "D002L-P1",
                    "status": "TERMINAL_PASS" if direct_fetch else "OFFLINE_REPLAY_ONLY",
                    "decision": (
                        "D002L_EXPOSURE_REGISTRY_SOURCE_COMPLETE"
                        if direct_fetch
                        else "OFFLINE_REPLAY_NOT_AUTHORIZED_FOR_LINEAGE_ADVANCE"
                    ),
                    "source_complete_registry": True,
                    "source_acquisition_mode": attempt["mode"],
                    "source_authenticity_for_lineage_advance": direct_fetch,
                    "lineage_advance_allowed": direct_fetch,
                    "next_legal_node": "D002L-P2" if direct_fetch else None,
                    "confirmatory_outcomes_ingested": False,
                    "canonical_run_authorized": False,
                },
            )
        return 0 if ns.fetch_official else 20
    except Exception as exc:
        reason = str(exc) if isinstance(exc, D002LExposureError) else f"{type(exc).__name__}:{exc}"
        if ns.status_out:
            _write_json(ns.status_out, blocked_result(reason, attempt=attempt))
        sys.stderr.write(f"D002L-P1 BLOCKED: {reason}\n")
        return 10


if __name__ == "__main__":
    raise SystemExit(main())
