# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Readiness gate subprocess integration check."""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
READINESS_SCRIPT = REPO_ROOT / "scripts" / "aar_pro_readiness.py"


def _run_readiness() -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, str(READINESS_SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_aar_pro_readiness_script_is_deterministic_and_complete() -> None:
    first = _run_readiness()
    second = _run_readiness()

    assert first == second
    assert first["schema_version"] == "AAR-PRO-V1-READINESS"
    assert first["status"] == "READY"
    assert math.isclose(
        first["precision_weighted_distance"],
        math.sqrt(5.0),
        abs_tol=1e-9,
    )
    assert first["compiled"] == [
        "core/dro_ara/engine.py",
        "geosync_hpc/control/action_result_comparator.py",
        "geosync_hpc/control/self_healing.py",
        "scripts/aar_pro_smoke.py",
    ]
