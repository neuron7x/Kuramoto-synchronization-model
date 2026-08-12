from pathlib import Path

from tools.research.validate_operator_contract import validate_operator_contract


def test_validate_operator_contract_validates() -> None:
    result = validate_operator_contract(Path("docs/operators/validate_operator.json"))

    assert result["status"] == "PASS"
    assert result["errors"] == []
    assert "S0_REPO_FACT" in result["status_tags"]
    assert "S5_PROXY" in result["status_tags"]


def test_normalize_operator_contract_validates() -> None:
    result = validate_operator_contract(Path("docs/operators/normalize_operator.json"))

    assert result["status"] == "PASS"
    assert result["errors"] == []
    assert "S0_REPO_FACT" in result["status_tags"]
    assert "S5_PROXY" in result["status_tags"]
