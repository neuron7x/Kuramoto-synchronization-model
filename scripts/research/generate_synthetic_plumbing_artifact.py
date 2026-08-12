#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Deterministic synthetic plumbing-proof artifact generator.

This is the smallest honest forward proof of the integrity pipeline:

    seed/formula -> data -> data hash -> real computation -> score ->
    baseline -> artifact (full lineage) -> validator -> test -> replay command

It fabricates **no empirical evidence**. The data is a closed-form synthetic
panel (no RNG, so the hash is byte-stable across platforms); the score is a real
computation (mean absolute off-diagonal Pearson correlation) on that synthetic
panel; the null baseline is a real cyclic-shift transform of the same panel.

The artifact is therefore honest by construction:

* ``claim_tier: INSTRUMENTED``  — synthetic data can instrument plumbing, never
  promote to an empirical tier (README promotion rule);
* ``score_source: computed``    — a real number was produced by a pinned method;
* ``falsification_status: NOT_APPLICABLE`` — no falsification/evidence is claimed;
* ``data_sha256``               — the hash of the committed synthetic panel;
* ``replay_command``            — re-runs this generator to reproduce it.

Run (this is also the replay command stamped into the artifact)::

    python scripts/research/generate_synthetic_plumbing_artifact.py
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "artifacts" / "runs" / "synthetic_plumbing_v1"
DATA_PATH = OUT_DIR / "synthetic_returns.csv"
ARTIFACT_PATH = OUT_DIR / "artifact.json"

N_ASSETS = 5
N_STEPS = 256
METHOD_VERSION = "synthetic-mean-abs-corr-v1"
REPLAY_COMMAND = "python scripts/research/generate_synthetic_plumbing_artifact.py"
RUN_ID = "SYNTHETIC-PLUMBING-V1"
TIMESTAMP_UTC = "1970-01-01T00:00:00Z"  # fixed: this artifact is reproducible, not timed
SEED = 42
CONFORMS_TO = "https://schemas.neuron7xlab.org/research/research_inference_artifact.schema.json"
SCHEMA_VERSION = "1.0.0"
RESEARCH_LINE = "synthetic_plumbing"


def synthetic_returns() -> NDArray[np.float64]:
    """Closed-form synthetic return panel — no RNG, byte-stable everywhere."""
    out = np.empty((N_STEPS, N_ASSETS), dtype=np.float64)
    for t in range(N_STEPS):
        for a in range(N_ASSETS):
            out[t, a] = 0.01 * math.sin(0.05 * t + a + SEED * 0.0) + 0.003 * math.cos(
                0.02 * t * (a + 1)
            )
    return out


def canonical_csv(panel: NDArray[np.float64]) -> str:
    """Fixed-format CSV so the data hash is identical on every platform."""
    header = ",".join(f"asset_{a}" for a in range(N_ASSETS))
    rows = [",".join(f"{panel[t, a]:.8f}" for a in range(N_ASSETS)) for t in range(N_STEPS)]
    return header + "\n" + "\n".join(rows) + "\n"


def mean_abs_offdiag_corr(panel: NDArray[np.float64]) -> float:
    """Real, deterministic score: mean |corr| over off-diagonal asset pairs."""
    corr = np.corrcoef(panel, rowvar=False)
    n = corr.shape[0]
    mask = ~np.eye(n, dtype=bool)
    return round(float(np.abs(corr[mask]).mean()), 10)


def cyclic_shift_null(panel: NDArray[np.float64]) -> float:
    """Real null baseline: same score on a per-column cyclic-shift surrogate."""
    shifted = np.column_stack([np.roll(panel[:, a], shift=(a + 1) * 7) for a in range(N_ASSETS)])
    return mean_abs_offdiag_corr(shifted)


def _git_sha() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=False, capture_output=True, text=True, cwd=ROOT
    )
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and len(value) == 40 else "0" * 40


def build() -> dict[str, object]:
    panel = synthetic_returns()
    csv_text = canonical_csv(panel)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(csv_text, encoding="utf-8")

    data_sha256 = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()
    config_sha256 = hashlib.sha256(
        f"{METHOD_VERSION}|{N_ASSETS}x{N_STEPS}|seed={SEED}".encode()
    ).hexdigest()
    score = mean_abs_offdiag_corr(panel)
    null_score = cyclic_shift_null(panel)

    return {
        "conforms_to": CONFORMS_TO,
        "schema_version": SCHEMA_VERSION,
        "research_line": RESEARCH_LINE,
        "run_id": RUN_ID,
        "git_sha": _git_sha(),
        "git_dirty": False,
        "data_sha256": data_sha256,
        "config_sha256": config_sha256,
        "seed": SEED,
        "timestamp_utc": TIMESTAMP_UTC,
        "input_window_sec": 1,
        "score": score,
        "uncertainty": 0.0,
        "decision": "OBSERVE",
        "claim_tier": "INSTRUMENTED",
        "falsification_status": "NOT_APPLICABLE",
        "artifact_role": "evidence",
        "score_source": "computed",
        "method_version": METHOD_VERSION,
        "baseline": f"cyclic_shift_null_mean_abs_corr={null_score:.6f}",
        "replay_command": REPLAY_COMMAND,
    }


def main() -> int:
    artifact = build()
    ARTIFACT_PATH.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {DATA_PATH.relative_to(ROOT)} and {ARTIFACT_PATH.relative_to(ROOT)}")
    print(f"  data_sha256={artifact['data_sha256']}")
    print(f"  score={artifact['score']}  baseline={artifact['baseline']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
