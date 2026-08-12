from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]


def _contract() -> dict[str, Any]:
    return json.loads(
        (ROOT / "contracts/dopamine_contract.v1.json").read_text(encoding="utf-8")
    )


def test_contract_checker_blocks_until_required_artifacts_exist(tmp_path: Path) -> None:
    module: Any = importlib.import_module("scripts.check_dopamine_contract")
    reasons = module.validate_required_artifacts(
        {"required_artifacts": ["missing/CONTRACT_VERDICT.json"]},
        tmp_path,
    )
    assert reasons == ["missing artifact: missing/CONTRACT_VERDICT.json"]


def test_contract_validator_passes_semantic_surface_only() -> None:
    module: Any = importlib.import_module("scripts.check_dopamine_contract")
    assert module.validate_contract(_contract(), ROOT, require_artifacts=False) == []


def test_contract_validator_rejects_claim_promotion_mutation() -> None:
    module: Any = importlib.import_module("scripts.check_dopamine_contract")
    mutated = copy.deepcopy(_contract())
    mutated["semantics"]["RAW_TD_RPE"]["market_claim_allowed"] = True
    reasons = module.validate_contract(mutated, ROOT, require_artifacts=False)
    assert any("promotion boundary" in reason for reason in reasons)


def test_contract_validator_rejects_missing_owner_and_empty_invariants() -> None:
    module: Any = importlib.import_module("scripts.check_dopamine_contract")
    mutated = copy.deepcopy(_contract())
    mutated["semantics"]["RAW_TD_RPE"]["owner"] = "missing/dopamine_surface.py"
    mutated["semantics"]["RAW_TD_RPE"]["required_invariants"] = []
    reasons = module.validate_contract(mutated, ROOT, require_artifacts=False)
    assert any("missing owner" in reason for reason in reasons)
    assert any("missing invariants" in reason for reason in reasons)
