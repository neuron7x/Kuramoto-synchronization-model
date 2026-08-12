#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from tools.cns_program.cns_contract import (
    CONFIG_PATH,
    DEPLOY_GATE_RESULT,
    REQUIRED_STATES,
)
from tools.cns_program.simple_yaml import load_yaml_file


def validate_protocol() -> dict[str, Any]:
    config = load_yaml_file(CONFIG_PATH)
    states = config.get("states", [])
    if not isinstance(states, list):
        states = []
    missing = [state for state in REQUIRED_STATES if state not in states]
    weights = config.get("metrics", {}).get("quality_weights", {})
    if not isinstance(weights, dict):
        weights = {}
    weight_sum = sum(float(value) for value in weights.values())
    thresholds = config.get("thresholds", {})
    if not isinstance(thresholds, dict):
        thresholds = {}
    threshold = float(thresholds.get("quality_score_min", 0.0))
    valid = not missing and abs(weight_sum - 1.0) < 1e-9 and 0.0 < threshold <= 1.0
    return {
        "valid": valid,
        "missing_states": missing,
        "weight_sum": weight_sum,
        "quality_score_min": threshold,
    }


def main() -> int:
    DEPLOY_GATE_RESULT.parent.mkdir(parents=True, exist_ok=True)
    protocol = validate_protocol()
    payload = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "deploy_ready": bool(protocol["valid"]),
        "protocol": protocol,
    }
    DEPLOY_GATE_RESULT.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["deploy_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
