from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/check_research_standard_contract.py"


def test_research_standard_contract_script_passes() -> None:
    result = subprocess.run([sys.executable, str(SCRIPT)], cwd=ROOT, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["standard_id"] == "geosync.research_standard.v1"
    assert payload["evidence_level"] == "HYPOTHESIS"
    assert payload["layers"] >= 5
    assert payload["manifests"] >= 4
    assert payload["waves"] == 4
