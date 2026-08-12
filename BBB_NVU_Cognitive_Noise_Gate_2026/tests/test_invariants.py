import hashlib
import itertools
import math
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import yaml

from BBB_NVU_Cognitive_Noise_Gate_2026.src.deterministic_engine import (
    DeterministicInferenceEngine,
    VALID_STATES,
    canonicalize_jcs,
)
from BBB_NVU_Cognitive_Noise_Gate_2026.tests.requirements import requirement

ROOT = Path(__file__).resolve().parents[1]
ENGINE = DeterministicInferenceEngine(ROOT / "config" / "risk_rules.yaml")
FIXED_TIME = "2026-06-03T00:00:00Z"
DOMAIN_KEYS = ["BSI", "NRI", "VML", "GRS", "CNI"]
GENERATIVE_VALUES = [
    -1_000_000.0,
    -0.1,
    0.0,
    24.9999,
    25.0,
    35.0,
    40.0,
    55.0,
    60.0,
    75.0,
    80.0,
    100.0,
    100.1,
    1_000_000.0,
    float("nan"),
    float("inf"),
    float("-inf"),
]
DomainVector = dict[str, float]
InvariantDoc = dict[str, Any]


def generated_domain_vectors(limit: int = 500) -> Iterator[DomainVector]:
    """Generate deterministic threshold, boundary, and corrupt math vectors."""
    produced = 0
    for key in DOMAIN_KEYS:
        for value in GENERATIVE_VALUES:
            vector = {domain: 50.0 for domain in DOMAIN_KEYS}
            vector[key] = value
            yield vector
            produced += 1
            if produced >= limit:
                return
    for values in itertools.product(GENERATIVE_VALUES[:8], repeat=2):
        vector = {domain: 50.0 for domain in DOMAIN_KEYS}
        vector["BSI"], vector["GRS"] = values
        yield vector
        produced += 1
        if produced >= limit:
            return


def recomposed_statement_digest(invariant: InvariantDoc) -> str:
    digest = cast(dict[str, Any], invariant["statement_digest"])
    assert digest["algorithm"] == "sha256"
    chunks = cast(list[str], digest["chunks"])
    assert len(chunks) == 8
    assert all(isinstance(chunk, str) and len(chunk) == 8 for chunk in chunks)
    return "".join(chunks)


@requirement("R002")
def test_inv_fail_closed_on_corrupted_math() -> None:
    for indices in generated_domain_vectors(limit=500):
        input_doc: dict[str, Any] = {
            "subject_id": "STRESS_TEST",
            "critical_data_invalid": False,
            "confidence": 1.0,
            "domain_indices": indices,
            "degradations": [],
        }

        risk_output, actions = ENGINE.evaluate_run(input_doc, FIXED_TIME)

        assert risk_output["risk_state"] in VALID_STATES
        has_corrupted_math = any(not math.isfinite(float(value)) for value in indices.values())
        has_out_of_contract_math = any(
            math.isfinite(float(value)) and (float(value) < 0 or float(value) > 100)
            for value in indices.values()
        )
        if has_corrupted_math or has_out_of_contract_math:
            assert risk_output["risk_state"] == "BLACK_INVALID"
            assert risk_output["confidence"] == 0.0
            assert actions
            assert all(action["prohibited_autonomous_execution"] for action in actions)


@requirement("R003")
def test_inv_deterministic_hash_stability() -> None:
    dict_a = {"BSI": 42.1, "VML": 62.0, "NRI": 28.5, "GRS": 48.0, "CNI": 31.0}
    items = list(dict_a.items())
    for permuted_items in itertools.islice(itertools.permutations(items), 50):
        dict_b = dict(permuted_items)
        assert canonicalize_jcs(dict_a) == canonicalize_jcs(dict_b)


@requirement("R002")
def test_inv_critical_invalid_zeroes_confidence_and_blocks_execution() -> None:
    risk_output, actions = ENGINE.evaluate_run(
        {
            "subject_id": "INVALID_TEST",
            "critical_data_invalid": True,
            "confidence": 1.0,
            "domain_indices": {"BSI": 20, "NRI": 15, "VML": 25, "GRS": 75, "CNI": 20},
            "degradations": [],
        },
        FIXED_TIME,
    )
    assert risk_output["risk_state"] == "BLACK_INVALID"
    assert risk_output["confidence"] == 0.0
    assert all(action["prohibited_autonomous_execution"] for action in actions)


@requirement("R004")
def test_inv_yaml_invariants_are_executable_bound() -> None:
    invariants = cast(
        dict[str, Any],
        yaml.safe_load(
            (ROOT / "invariants.yaml").read_text(encoding="utf-8")
        ),
    )
    for invariant in cast(list[InvariantDoc], invariants["invariants"]):
        assert str(invariant["requirement_id"]).startswith("R")
        assert invariant["test_refs"]
        payload = f"{invariant['statement']}\n{invariant['enforcement']}".encode("utf-8")
        assert recomposed_statement_digest(invariant) == hashlib.sha256(
            payload
        ).hexdigest()
