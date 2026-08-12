#!/usr/bin/env python3
"""Diff-bound falsifier for the ricci-microstructure-v1-scaffolding acceptor.

Inverts the no-overclaim contract: the artifact JSON Schema MUST reject a payload
whose falsification_status is ALPHA_FOUND (a forbidden market-mythology status).
If the schema were weakened to admit it, validate_artifact_payload returns no
errors and this script exits non-zero.

Exit 0  -> schema rejects the forbidden ALPHA_FOUND artifact (asserted-healthy).
Exit 1  -> schema accepted an overclaim artifact (boundary broken).
"""

from __future__ import annotations

import sys

from geosync_research.lines.ricci_microstructure_v1.artifact import validate_artifact_payload


def main() -> int:
    payload = {
        "run_id": "x",
        "schema_version": "ricci_microstructure_artifact.v1",
        "kernel_version": "ricci_kernel.v2-weighted-sizemeasure",
        "source": "BINANCE_FUTURES_DEPTH",
        "source_class": "BINANCE_PUBLIC_DEPTH",
        "license_status": "PUBLIC_NO_LICENSE",
        "config_hash": "a" * 64,
        "config_sha256": "a" * 64,
        "data_sha256": "b" * 64,
        "collector_sha256": "e" * 64,
        "git_sha": "c" * 40,
        "dirty_git": False,
        "seed": 1337,
        "mean_curvature": -0.1,
        "observed_count": 600,
        "null_mean": -0.2,
        "null_std": 0.1,
        "p_value": 0.4,
        "cliffs_delta": 0.2,
        "effect_size_class": "small",
        "null_model_type": "iaaft",
        "n_surrogates": 1000,
        "falsification_status": "ALPHA_FOUND",
        "forbidden_claims_absent": False,
        "replay_command": (
            "geosync-research run --line ricci_microstructure_v1 --config c --data d --out o"
        ),
        "timestamp_utc": "2026-01-01T00:00:00Z",
        "claim_tier": "T3/NOVEL/EXPLORATORY/FALSIFIABLE",
    }
    if not validate_artifact_payload(payload):
        print("FALSIFIED: schema accepted a forbidden ALPHA_FOUND artifact", file=sys.stderr)
        return 1
    print("OK: schema rejects the forbidden ALPHA_FOUND artifact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
