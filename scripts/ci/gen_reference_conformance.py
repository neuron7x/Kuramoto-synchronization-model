#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Reference-standard conformance certificate.

Derives — from the *actual* repository state, never a rubber stamp — whether the
neuro/physics evidence corpus conforms to the five invariant laws of the
verified-inference reference standard (docs/phd/13_reference_inference_standard.md).

Each law is checked against facts in the neuro ledger and the presence of the
machine-checked gate that enforces it. The certificate certifies *evidence
discipline / admissibility*, NOT empirical truth.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / ".claude/neuro/NEURO_OPERATIONALIZATION_LEDGER.yaml"
OUT = ROOT / "artifacts/academy_fellow/reference_conformance_certificate.json"


def _entries() -> list[dict]:
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


def _has(rel: str) -> bool:
    return (ROOT / rel).exists()


def main() -> int:
    e = _entries()
    op = [x for x in e if x["classification"] == "OPERATIONAL"]
    partial = [x for x in e if x["classification"] == "PARTIAL"]

    def nonempty(x: object) -> bool:
        return isinstance(x, str) and bool(x.strip())

    open_missing = sum(len(x.get("missing_tests") or []) for x in e)
    op_without_inv = [x["id"] for x in op if not any(x.get("inv_refs") or [])]
    op_without_test = [x["id"] for x in op if not (x.get("existing_tests") or [])]
    op_without_fals = [x["id"] for x in op if not nonempty(x.get("falsifier"))]
    claimed_without_fals = [x["id"] for x in (op + partial) if not nonempty(x.get("falsifier"))]
    partial_keep = [x["id"] for x in partial if x.get("remediation_action") == "KEEP"]

    # Each law: (id, statement, enforcing gate, PASS bool, evidence).
    laws = [
        {
            "law": "L1-admissibility-not-promotion",
            "statement": "A witnessed mechanism is admissible but is NOT promoted to a claim "
            "tier unless it is fully bound (invariant + contract + falsifier + test).",
            "enforcing_gate": "tools/audit/neuro_symbolic_audit.py",
            "pass": open_missing == 0,
            "evidence": {"open_missing_tests": open_missing},
        },
        {
            "law": "L2-no-promotion-without-invariant",
            "statement": "No OPERATIONAL claim without >=1 INV-* binding from CLAUDE.md.",
            "enforcing_gate": "tools/audit/neuro_symbolic_audit.py",
            "pass": not op_without_inv,
            "evidence": {"operational_without_inv_ref": op_without_inv},
        },
        {
            "law": "L3-falsification-first",
            "statement": "Every OPERATIONAL/PARTIAL claim declares an executable falsifier.",
            "enforcing_gate": "scripts/ci/check_falsifier_ledger.py",
            "pass": not claimed_without_fals,
            "evidence": {"claims_without_falsifier": claimed_without_fals},
        },
        {
            "law": "L4-no-overclaim-wall",
            "statement": "Biological-equivalence and product-category overclaims are firewalled "
            "in runtime source and on the canonical doc surface.",
            "enforcing_gate": "scripts/ci/check_neuro_claim_boundary.py + check_claim_boundary.py",
            "pass": _has("scripts/ci/check_neuro_claim_boundary.py")
            and _has("scripts/ci/check_claim_boundary.py"),
            "evidence": {
                "neuro_wall": _has("scripts/ci/check_neuro_claim_boundary.py"),
                "product_wall": _has("scripts/ci/check_claim_boundary.py"),
            },
        },
        {
            "law": "L5-one-command-reproducibility",
            "statement": "The full evidence battery runs from a single command (make phd-evidence).",
            "enforcing_gate": "scripts/ci/phd_evidence.sh",
            "pass": _has("scripts/ci/phd_evidence.sh"),
            "evidence": {"phd_evidence_script": _has("scripts/ci/phd_evidence.sh")},
        },
        {
            "law": "L6-witness-completeness",
            "statement": "Every OPERATIONAL claim carries >=1 existing witness test and a non-empty "
            "falsifier; no claim rests on test exit-codes alone.",
            "enforcing_gate": "scripts/ci/check_invariant_source_binding.py",
            "pass": not op_without_test and not op_without_fals,
            "evidence": {
                "operational_without_test": op_without_test,
                "operational_without_falsifier": op_without_fals,
            },
        },
        {
            "law": "L7-partial-has-remediation",
            "statement": "Every PARTIAL claim declares an active (non-KEEP) remediation.",
            "enforcing_gate": "tools/audit/neuro_symbolic_audit.py",
            "pass": not partial_keep,
            "evidence": {"partial_with_keep": partial_keep},
        },
    ]

    conformant = all(law["pass"] for law in laws)
    from collections import Counter

    cert = {
        "schema": "academy-fellow/reference_conformance_certificate@v1",
        "standard": "docs/phd/13_reference_inference_standard.md",
        "source": ".claude/neuro/NEURO_OPERATIONALIZATION_LEDGER.yaml",
        "generated_by": "scripts/ci/gen_reference_conformance.py",
        "verdict": "CONFORMANT" if conformant else "NON_CONFORMANT",
        "tier": "evidence-discipline / admissibility — NOT empirical truth",
        "ledger_distribution": dict(Counter(x["classification"] for x in e)),
        "laws": laws,
        "status_discipline": (
            "Conformance to a reference standard of evidence discipline, reproducibility, and "
            "restraint. NOT a claim of a Distinguished-Professor-level result, and NOT a claim of "
            "empirical/scientific truth."
        ),
        "non_claims": [
            "No biological equivalence.",
            "No universal physics of markets.",
            "No alpha/profitability/edge. No B.wheel=0.",
            "Synthetic-only witnesses; no real L2 dataset/replay implied.",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(cert, indent=2, ensure_ascii=False) + "\n")
    print(
        f"reference conformance: {cert['verdict']} ({sum(law['pass'] for law in laws)}/{len(laws)} laws)"
    )
    if not conformant:
        for law in laws:
            if not law["pass"]:
                print(f"  FAIL {law['law']}: {law['evidence']}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
