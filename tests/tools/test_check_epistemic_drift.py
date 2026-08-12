from __future__ import annotations

from scripts.check_epistemic_drift import _extract_claim_count, _extract_readme_invariants


def test_extract_readme_invariants() -> None:
    text = "[![invariants-97](https://img.shields.io/badge/invariants-97-critical)]"
    assert _extract_readme_invariants(text) == 97


def test_extract_claim_count() -> None:
    text = '| C-INV-COUNT | "97 invariants in `.claude/physics/INVARIANTS.yaml`" ' "| `FACT` |"
    assert _extract_claim_count(text) == 97
