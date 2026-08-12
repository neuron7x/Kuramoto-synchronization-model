from __future__ import annotations

from pathlib import Path

from tools.research.validate_cme_iteration_contract import validate_contract


def test_cme_iteration_contract_valid() -> None:
    result = validate_contract(Path("docs/CME_ITERATION_0001.json"))

    assert result["status"] == "PASS", result["errors"]
