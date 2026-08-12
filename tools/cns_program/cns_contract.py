from __future__ import annotations

from pathlib import Path

CONFIG_PATH = Path("conf/cns_program/default.yaml")
INVARIANTS_PATH = Path("conf/cns_program/invariants.yaml")
CONTRACT_REPORT = Path("reports/CNS_RELEASE_GATE_CONTRACT.md")
DEPLOY_GATE_RESULT = Path("results/cns_deploy_gate.json")
RELEASE_MANIFEST_RESULT = Path("results/cns_release_manifest.json")
MANIFEST_VERIFICATION_RESULT = Path("results/cns_manifest_verification.json")
REPORTS_CONTRACT_RESULT = Path("results/cns_reports_contract.json")
QUALITY_GATE_RESULT = Path("results/cns_quality_gate.json")

REQUIRED_STATES = (
    "ingest",
    "validate",
    "render",
    "manifest",
    "verify",
    "report",
    "release_decision",
)

MANIFEST_FILES = (
    Path(".github/workflows/cns-release-gate.yml"),
    CONFIG_PATH,
    INVARIANTS_PATH,
    CONTRACT_REPORT,
    Path("tools/cns_program/cns_contract.py"),
    Path("tools/cns_program/deploy_release_gate.py"),
    Path("tools/cns_program/build_release_manifest.py"),
    Path("tools/cns_program/verify_release_manifest.py"),
    Path("tools/cns_program/verify_reports_contract.py"),
    Path("tools/cns_program/quality_gate.py"),
    Path("tools/cns_program/simple_yaml.py"),
)

REQUIRED_REPORTS = (CONTRACT_REPORT,)
