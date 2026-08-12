#!/usr/bin/env python3
"""Local sandbox adversarial auditor for the deterministic BBB-NVU engine."""

from __future__ import annotations

import argparse
import json
import random
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_RULES = ROOT / "config" / "risk_rules.yaml"
DEFAULT_OUTPUT = ROOT / "tests" / "adversarial_golden_vectors.json"
CRITICAL_DEGRADATION_PAYLOADS = [
    ["UNKNOWN_PROVENANCE"],
    ["SOURCE_CONFLICT"],
    ["CLOCK_SKEW_DETECTED"],
    ["OUT_OF_DISTRIBUTION"],
    ["UNKNOWN_PROVENANCE", "CLOCK_SKEW_DETECTED"],
]


class AdversarialAuditor:
    """Creator/verifier loop for schema-shaped adversarial vectors."""

    def __init__(self, rules_path: str | Path = DEFAULT_RULES, seed: int = 20260603):
        from BBB_NVU_Cognitive_Noise_Gate_2026.src.deterministic_engine import (
            DeterministicInferenceEngine,
        )

        self.engine = DeterministicInferenceEngine(rules_path)
        self.random = random.Random(seed)
        self.base_vector: dict[str, Any] = {
            "subject_id": "ADV_001",
            "critical_data_invalid": False,
            "confidence": 1.0,
            "domain_indices": {"BSI": 30, "NRI": 25, "VML": 30, "GRS": 60, "CNI": 20},
            "degradations": [],
        }

    def generate_attack_vector(self, iteration: int) -> dict[str, Any]:
        """Generate deterministic adversarial mutations around known surfaces."""
        mutated = deepcopy(self.base_vector)
        attack_type = iteration % 6

        if attack_type == 0:
            mutated["critical_data_invalid"] = True
            mutated["confidence"] = 999.0
        elif attack_type == 1:
            mutated["domain_indices"] = {}
        elif attack_type == 2:
            mutated["domain_indices"]["BSI"] = float("nan")
        elif attack_type == 3:
            mutated["domain_indices"]["NRI"] = 1_000_000.0
        elif attack_type == 4:
            mutated["degradations"] = self.random.choice(CRITICAL_DEGRADATION_PAYLOADS)
        else:
            epsilon = 0.0001
            mutated["domain_indices"] = {
                "BSI": 35 - epsilon,
                "NRI": 30 - epsilon,
                "VML": 35 - epsilon,
                "GRS": 55 + epsilon,
                "CNI": 30 - epsilon,
            }
            mutated["degradations"] = ["UNKNOWN_PROVENANCE"]

        return mutated

    def verify_defense(
        self,
        input_vector: dict[str, Any],
        risk: dict[str, Any],
        actions: list[dict[str, Any]],
    ) -> None:
        """Assert that adversarial payloads cannot hide as GREEN_STABLE."""
        if input_vector.get("critical_data_invalid"):
            assert (
                risk["risk_state"] == "BLACK_INVALID"
            ), "critical_data_invalid bypassed fail-closed gate"
            assert risk["confidence"] == 0.0, "invalid input did not zero confidence"

        if input_vector.get("degradations"):
            assert risk["risk_state"] != "GREEN_STABLE", "degradation payload produced GREEN_STABLE"

        if risk["risk_state"] in {"BLACK_INVALID", "RED_CRITICAL"}:
            assert actions
            assert all(action["prohibited_autonomous_execution"] for action in actions)

        if risk["confidence"] < 0.70:
            assert risk["risk_state"] != "GREEN_STABLE", "low confidence produced GREEN_STABLE"

    def run_campaign(self, iterations: int = 100) -> list[dict[str, Any]]:
        """Run a deterministic adversarial campaign and return golden vectors."""
        golden_vectors: list[dict[str, Any]] = []
        for iteration in range(iterations):
            attack_vector = self.generate_attack_vector(iteration)
            risk, actions = self.engine.evaluate_run(attack_vector, "2026-06-03T00:00:00Z")
            self.verify_defense(attack_vector, risk, actions)
            golden_vectors.append(
                {
                    "input": attack_vector,
                    "risk_state": risk["risk_state"],
                    "confidence": risk["confidence"],
                }
            )
        return golden_vectors


def main() -> int:
    from BBB_NVU_Cognitive_Noise_Gate_2026.src.deterministic_engine import hashable_json_value

    parser = argparse.ArgumentParser(description="Run deterministic adversarial sandbox campaign.")
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    vectors = AdversarialAuditor().run_campaign(args.iterations)
    args.output.write_text(
        json.dumps(
            hashable_json_value(vectors),
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {"iterations": args.iterations, "bypasses": 0, "output": str(args.output)},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
