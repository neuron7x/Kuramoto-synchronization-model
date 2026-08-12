#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QUALITY_GATE_RESULT = ROOT / "results/cns_quality_gate.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def regression_quality_artifact_passes() -> None:
    require(
        QUALITY_GATE_RESULT.exists(),
        f"missing quality gate artifact: {QUALITY_GATE_RESULT}",
    )
    payload = json.loads(QUALITY_GATE_RESULT.read_text(encoding="utf-8"))
    require(isinstance(payload, dict), "quality gate payload is not a JSON object")
    require(payload.get("passed") is True, "quality gate did not pass")
    require(payload.get("quality_score") == 1.0, "quality score is not 1.0")
    require(payload.get("threshold") == 0.80, "quality threshold changed")
    metrics = payload.get("metrics")
    require(isinstance(metrics, list) and len(metrics) == 4, "quality metrics shape changed")


def main() -> int:
    regression_quality_artifact_passes()
    print(json.dumps({"cns_regression_gate": "PASS"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
