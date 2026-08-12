from __future__ import annotations

from scripts.validate_financial_contract import validate_financial_data


def test_validate_financial_contract_script_passes_fixture() -> None:
    assert validate_financial_data() == []
