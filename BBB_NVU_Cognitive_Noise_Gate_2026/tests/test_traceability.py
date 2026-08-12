# ruff: noqa: I001

from BBB_NVU_Cognitive_Noise_Gate_2026.tests.requirements import requirement
from BBB_NVU_Cognitive_Noise_Gate_2026.tools.traceability import (
    collect_traceability,
    read_generated_matrix,
)


@requirement("R003")
def test_generated_traceability_matrix_matches_annotated_tests() -> None:
    assert read_generated_matrix() == collect_traceability()
