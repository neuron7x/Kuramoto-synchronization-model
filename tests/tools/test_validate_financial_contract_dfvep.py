from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.validate_financial_contract import main


def test_dfvep_manifest_emitted() -> None:
    assert main() == 0
    p = Path("artifacts/financial_verification_manifest.json")
    assert p.exists()
    payload: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    assert payload["protocol_version"] == "DFV-EP v1.0"
    assert payload["verdict"] == "EP_PARITY_PASSED"
    assert payload["verification_metrics"]["epistemic_drift_delta"] <= 1e-6
