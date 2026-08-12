# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Operational smoke test for the AAR-PRO-V1 one-command example."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
SMOKE_SCRIPT = REPO_ROOT / "scripts" / "aar_pro_smoke.py"


def _run_smoke() -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, str(SMOKE_SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_aar_pro_smoke_script_is_deterministic_and_sanctioned() -> None:
    first = _run_smoke()
    second = _run_smoke()

    assert first == second
    assert first["schema_version"] == "AAR-PRO-V1-SMOKE"
    assert first["status"] == "SANCTIONED_MATCH"
    assert first["accepted"] is True
    assert first["rollback_required"] is False
    assert first["model_update_allowed"] is True
    assert first["recovery_action"] == "ALLOW_MODEL_UPDATE"
    assert first["chain_verified"] is True
    assert first["episode_closed"] is True
    assert first["last_phase"] == "MEMORY_ANCHORED"
    assert first["phase_count"] == 7
    assert isinstance(first["evidence_digest"], str)
    assert len(first["evidence_digest"]) == 64
