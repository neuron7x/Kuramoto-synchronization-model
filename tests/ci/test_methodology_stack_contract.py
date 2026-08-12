from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs" / "governance" / "methodology_stack_contract.md"

REQUIRED_TOKENS = (
    "adaptive verified operation",
    "observability-first instrumentation",
    "alternative-model elimination",
    "phenomenon-to-engineering transfer",
    "target lock",
    "observation window",
    "alternative models",
    "discriminating test",
    "controlled parameters",
    "negative evidence path",
    "claim boundary",
    "Pending CI blocks merge interpretation.",
)


def validate_contract_text(text: str) -> list[str]:
    missing = [token for token in REQUIRED_TOKENS if token not in text]
    if "No claim may skip levels." not in text:
        missing.append("No claim may skip levels.")
    return missing


def test_methodology_stack_contract_contains_required_controls() -> None:
    missing = validate_contract_text(CONTRACT.read_text(encoding="utf-8"))
    assert missing == []


def test_methodology_stack_contract_fails_closed_on_missing_control() -> None:
    text = CONTRACT.read_text(encoding="utf-8").replace("negative evidence path", "")
    assert "negative evidence path" in validate_contract_text(text)
