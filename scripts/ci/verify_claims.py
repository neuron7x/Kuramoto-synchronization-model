#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY = ROOT / "claims/ontology.json"
THESIS = ROOT / "docs/RESEARCH_THESIS.md"
BOUNDARY = ROOT / "scripts/ci/check_claim_boundary.py"

REQUIRED_TIERS = {"THEOREM", "INVARIANT", "EMPIRICAL", "HYPOTHESIS", "METAPHOR", "RETIRED", "QUARANTINED"}
REQUIRED_STATUSES = {"RESEARCH_ONLY", "MEASUREMENT_SYSTEM", "FALSIFICATION_FIRST", "OPEN_RESEARCH_STANDARD_CANDIDATE", "GEOMETRIC_REGIME_LAB", "EVIDENCE_BOUND_ARCHITECTURE"}


def _load_ontology() -> dict[str, Any]:
    value = json.loads(ONTOLOGY.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("ontology must be a JSON object")
    return value


def _validate_ontology(value: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if value.get("schema_version") != "1.0.0":
        errors.append("ontology schema_version must be 1.0.0")
    tiers = value.get("tiers")
    if not isinstance(tiers, list):
        return ["ontology tiers must be a list"]
    tier_ids = {str(item.get("id")) for item in tiers if isinstance(item, dict)}
    missing = sorted(REQUIRED_TIERS.difference(tier_ids))
    if missing:
        errors.append(f"missing tiers: {missing}")
    if value.get("default_new_claim_tier") != "HYPOTHESIS":
        errors.append("default_new_claim_tier must be HYPOTHESIS")
    statuses = set(value.get("allowed_default_status", []))
    if not REQUIRED_STATUSES.issubset(statuses):
        errors.append("allowed_default_status incomplete")
    for item in tiers:
        if not isinstance(item, dict):
            errors.append("tier entry must be an object")
            continue
        for key in ("id", "meaning", "requires_evidence_path", "public_headline_allowed"):
            if key not in item:
                errors.append(f"tier {item.get('id', '<missing>')} missing {key}")
    return errors


def _validate_thesis() -> list[str]:
    errors: list[str] = []
    if not THESIS.exists():
        return ["docs/RESEARCH_THESIS.md missing"]
    text = THESIS.read_text(encoding="utf-8")
    for token in REQUIRED_STATUSES:
        if token not in text:
            errors.append(f"research thesis missing status token: {token}")
    for token in ("claim_id -> tier -> domain -> evidence_path -> falsifier -> gate -> verdict", "Stop rule"):
        if token not in text:
            errors.append(f"research thesis missing contract phrase: {token}")
    return errors


def _run_boundary_gate() -> list[str]:
    result = subprocess.run([sys.executable, str(BOUNDARY)], cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode == 0:
        return []
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    return ["claim boundary gate failed", output.strip()]


def validate() -> list[str]:
    errors: list[str] = []
    if not ONTOLOGY.exists():
        errors.append("claims/ontology.json missing")
    else:
        errors.extend(_validate_ontology(_load_ontology()))
    errors.extend(_validate_thesis())
    errors.extend(_run_boundary_gate())
    return errors


def main() -> int:
    errors = validate()
    if errors:
        print(json.dumps({"status": "FAIL", "errors": errors}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps({"status": "PASS", "ontology": str(ONTOLOGY.relative_to(ROOT)), "thesis": str(THESIS.relative_to(ROOT))}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
