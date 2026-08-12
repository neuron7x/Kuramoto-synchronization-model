from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ci/verify_claims.py"
ONTOLOGY = ROOT / "claims/ontology.json"
THESIS = ROOT / "docs/RESEARCH_THESIS.md"


def test_verify_claims_passes_committed_claim_governance_seed() -> None:
    result = subprocess.run([sys.executable, str(SCRIPT)], cwd=ROOT, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["ontology"] == "claims/ontology.json"
    assert payload["thesis"] == "docs/RESEARCH_THESIS.md"


def test_claim_ontology_contains_required_tiers() -> None:
    payload = json.loads(ONTOLOGY.read_text(encoding="utf-8"))
    tiers = {entry["id"] for entry in payload["tiers"]}
    assert {"THEOREM", "INVARIANT", "EMPIRICAL", "HYPOTHESIS", "METAPHOR", "RETIRED", "QUARANTINED"}.issubset(tiers)
    assert payload["default_new_claim_tier"] == "HYPOTHESIS"


def test_research_thesis_contains_trace_contract() -> None:
    text = THESIS.read_text(encoding="utf-8")
    assert "claim_id -> tier -> domain -> evidence_path -> falsifier -> gate -> verdict" in text
    assert "OPEN_RESEARCH_STANDARD_CANDIDATE" in text
    assert "Stop rule" in text
