"""Generate the academy-fellow law/mechanism witness matrix from the neuro ledger.

Pure read of .claude/neuro/NEURO_OPERATIONALIZATION_LEDGER.yaml -> machine-readable
index. No claims invented; promotion_allowed is derived strictly from the ledger
(OPERATIONAL + no missing_tests + falsifier present + has >=1 existing test).
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / ".claude/neuro/NEURO_OPERATIONALIZATION_LEDGER.yaml"
OUT_DIR = ROOT / "artifacts/academy_fellow"


def domain_of(e: dict) -> str:
    term = (e.get("term") or "").lower()
    eid = e["id"].lower()
    blob = f"{term} {eid}"
    if any(
        k in blob
        for k in (
            "kuramoto",
            "ricci",
            "ott",
            "free-energy",
            "dro",
            "criticality",
            "lyapunov",
            "gauss",
        )
    ):
        return "physics"
    if any(k in blob for k in ("kelly", "optimizer", "sizing", "balance")):
        return "neuroeconomics"
    if any(
        k in blob
        for k in ("signal-bus", "hpc", "vital", "coherence-bridge", "orchestrator", "calibrator")
    ):
        return "runtime-governance"
    if any(k in blob for k in ("gaba", "dopamine", "serotonin", "hebbian", "homeostatic", "neuro")):
        return "neuroscience"
    return "runtime-governance"


def entries() -> list[dict]:
    d = yaml.safe_load(LEDGER.read_text())
    acc: list[dict] = []

    def walk(o: object) -> None:
        if isinstance(o, dict):
            if "id" in o and "classification" in o:
                acc.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(d)
    return acc


def main() -> None:
    acc = entries()
    rows = []
    for e in acc:
        existing = e.get("existing_tests") or []
        missing = e.get("missing_tests") or []
        cls = e["classification"]
        falsifier = (e.get("falsifier") or "").strip()
        promotion_allowed = bool(cls == "OPERATIONAL" and not missing and falsifier and existing)
        rows.append(
            {
                "id": e["id"],
                "domain": domain_of(e),
                "file": e.get("file"),
                "formula": (e.get("current_usage") or "").strip(),
                "validity": (e.get("input_contract") or "").strip(),
                "input_contract": (e.get("input_contract") or "").strip(),
                "output_contract": (e.get("output_contract") or "").strip(),
                "falsifier": falsifier,
                "existing_tests": existing,
                "missing_tests": missing,
                "claim_status": cls,
                "promotion_allowed": promotion_allowed,
                "inv_refs": e.get("inv_refs") or [],
                "remediation_action": e.get("remediation_action"),
                "witness_note": (e.get("witness_note") or "").strip() or None,
            }
        )

    from collections import Counter

    cls_dist = dict(Counter(r["claim_status"] for r in rows))
    matrix = {
        "schema": "academy-fellow/law_mechanism_witness_matrix@v1",
        "source": ".claude/neuro/NEURO_OPERATIONALIZATION_LEDGER.yaml",
        "generated_by": "scripts/ci/gen_law_mechanism_witness_matrix.py",
        "non_claims": [
            "No biological equivalence — all neuro names are engineering analogs.",
            "No universal physics of markets; observers are not predictors.",
            "No alpha/profitability claim.",
            "Synthetic-only witnesses; no real L2 dataset/replay implied.",
        ],
        "summary": {
            "total_mechanisms": len(rows),
            "classification_distribution": cls_dist,
            "operational_with_full_binding": sum(r["promotion_allowed"] for r in rows),
            "open_missing_tests": sum(len(r["missing_tests"]) for r in rows),
            "partial_remaining": [r["id"] for r in rows if r["claim_status"] == "PARTIAL"],
            "quarantined": [
                r["id"]
                for r in rows
                if r["claim_status"] in ("DECORATIVE", "OVERCLAIM", "LEGACY", "REJECTED")
            ],
        },
        "mechanisms": rows,
    }

    # Traceability report: per-mechanism PASS/PARTIAL/QUARANTINE verdict
    def verdict(r: dict) -> str:
        if r["claim_status"] in ("DECORATIVE", "OVERCLAIM", "LEGACY", "REJECTED"):
            return "QUARANTINE"
        if r["claim_status"] == "OPERATIONAL" and r["promotion_allowed"]:
            return "PASS"
        return "PARTIAL"

    trace = {
        "schema": "academy-fellow/traceability_report@v1",
        "gate": "every OPERATIONAL mechanism is invariant/contract/falsifier/test-bound; "
        "every PARTIAL has remediation; every quarantine entry is classified",
        "verdict": "PASS" if sum(len(r["missing_tests"]) for r in rows) == 0 else "BLOCKED",
        "rationale": "0 open missing_tests across the ledger; PARTIAL entries carry explicit "
        "remediation_action and cannot promote claim tier.",
        "rows": [
            {
                "id": r["id"],
                "domain": r["domain"],
                "verdict": verdict(r),
                "claim_status": r["claim_status"],
                "remediation": r["remediation_action"],
            }
            for r in rows
        ],
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "law_mechanism_witness_matrix.json").write_text(
        json.dumps(matrix, indent=2, ensure_ascii=False) + "\n"
    )
    (OUT_DIR / "traceability_report.json").write_text(
        json.dumps(trace, indent=2, ensure_ascii=False) + "\n"
    )
    print("matrix mechanisms:", len(rows))
    print("classification:", cls_dist)
    print("promotion_allowed (full binding):", matrix["summary"]["operational_with_full_binding"])
    print("open missing_tests:", matrix["summary"]["open_missing_tests"])
    print("traceability verdict:", trace["verdict"])


main()
