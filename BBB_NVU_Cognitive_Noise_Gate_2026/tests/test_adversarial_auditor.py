# ruff: noqa: I001

from typing import Any

from BBB_NVU_Cognitive_Noise_Gate_2026.scripts.adversarial_auditor import AdversarialAuditor
from BBB_NVU_Cognitive_Noise_Gate_2026.tests.requirements import requirement


def has_invalid_math(vector: dict[str, Any]) -> bool:
    domain_indices = vector["input"].get("domain_indices", {})
    if not isinstance(domain_indices, dict):
        return False
    return any(str(value) == "nan" for value in domain_indices.values())


def has_critical_invalid_flag(vector: dict[str, Any]) -> bool:
    return bool(vector["input"].get("critical_data_invalid"))


@requirement("R002")
def test_adversarial_sandbox_campaign_has_zero_bypasses() -> None:
    vectors: list[dict[str, Any]] = AdversarialAuditor().run_campaign(iterations=60)
    assert vectors
    assert all(
        vector["risk_state"] != "GREEN_STABLE"
        for vector in vectors
        if vector["input"].get("degradations")
    )
    assert all(
        vector["risk_state"] == "BLACK_INVALID"
        for vector in vectors
        if has_critical_invalid_flag(vector) or has_invalid_math(vector)
    )
