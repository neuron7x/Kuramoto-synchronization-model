# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Machine-readable tracker for the 7-task value uplift execution.

Run:
    python tools/value_uplift_tracker.py
    -> reports/value_uplift_tracker.json

The tracker is a declarative checklist: each task has ``status`` and
``evidence``. CI gates can read this file and fail the build if any
task is required but still ``pending``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TASKS: tuple[str, ...] = (
    "independent_reference_solver_parity",
    "property_based_invariant_suite",
    "ci_invariant_gate",
    "benchmark_matrix_snapshots",
    "regime_predictor_calibration",
    "failure_injection_protocol",
    "one_command_repro_pack",
)


def build_tracker() -> dict[str, Any]:
    """Return a fresh tracker payload with all tasks pending."""
    return {
        "target_value_usd": 30000,
        "tasks": [{"id": t, "status": "pending", "evidence": ""} for t in TASKS],
        "completion_ratio": 0.0,
    }


if __name__ == "__main__":
    payload = build_tracker()
    out = Path("reports/value_uplift_tracker.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
