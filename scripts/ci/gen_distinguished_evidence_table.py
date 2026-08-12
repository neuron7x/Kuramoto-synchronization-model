#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Generate the international-standard distinguished evidence table.

Pure read of the neuro operationalization ledger -> a machine-readable table
mapping every mechanism to: contribution, standard_anchor, file, test, gate,
falsifier, limitation, replay. No claim is invented; the standard_anchor and
the claim-tier are derived strictly from the ledger classification, NOT
asserted. OPERATIONAL maps to the "executable-witness / Results-Reproduced"
tier; PARTIAL/DECORATIVE/OVERCLAIM/LEGACY/REJECTED stay at admissibility tiers.

Standards referenced (anchors, not endorsements):
  * Popper — falsifiability as the demarcation criterion.
  * ACM Artifact Review & Badging v1.1 — Functional / Reproduced tiers.
  * FAIR (Wilkinson et al. 2016) — findable/accessible/interoperable/reusable.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / ".claude/neuro/NEURO_OPERATIONALIZATION_LEDGER.yaml"
OUT = ROOT / "artifacts/academy_fellow/distinguished_evidence_table.json"

# Claim-tier -> standard anchor. Derived from classification; never upgraded.
TIER_ANCHOR: dict[str, str] = {
    "OPERATIONAL": (
        "Popperian falsifiability + executable witness (ACM 'Results Reproduced' "
        "tier): invariant-bound, INV-* referenced, fail-closed CI gate."
    ),
    "PARTIAL": (
        "Admissibility only (ACM 'Functional' tier): witnessed but NOT claim-tier "
        "promoted — open remediation; no INV-* binding or open gap."
    ),
    "DECORATIVE": "Quarantined naming (non-claim): engineering analog, not a modelled mechanism.",
    "OVERCLAIM": "Quarantined overclaim: forbidden until artifact tier permits.",
    "LEGACY": "Frozen legacy record: retained for audit trail, not a live claim.",
    "REJECTED": "Rejected hypothesis: negative evidence, retained as scientific value.",
}

# The fail-closed gate that governs each domain (all exist in-repo).
DOMAIN_GATE: dict[str, str] = {
    "physics": "scripts/ci/check_invariant_source_binding.py + check_falsifier_ledger.py",
    "neuroscience": "scripts/ci/check_neuro_claim_boundary.py + tools/audit/neuro_symbolic_audit.py",
    "neuroeconomics": "tools/audit/neuro_symbolic_audit.py",
    "runtime-governance": "scripts/ci/check_phd_traceability.py + tools/audit/neuro_symbolic_audit.py",
}


def domain_of(e: dict) -> str:
    blob = f"{(e.get('term') or '').lower()} {e['id'].lower()}"
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


def replay_for(tests: list[str]) -> str:
    if not tests:
        return "(no executable witness — admissibility entry only)"
    return "PYTHONPATH=. python -m pytest " + " ".join(tests)


def limitation_for(e: dict) -> str:
    note = (e.get("witness_note") or "").strip()
    if note:
        return note
    reason = (e.get("reason") or "").strip()
    return reason or "See limitation ledger (docs/phd/04_limitation_ledger.md)."


def main() -> None:
    # Fail-closed integrity gate FIRST: derive tiers only from a ledger with no
    # fake promotion (OPERATIONAL w/o a resolving INV+test+falsifier; PARTIAL
    # claiming an INV binding; un-quarantined DECORATIVE on a runtime path).
    # Refuse to emit an evidence table built on a contradictory ledger.
    from scripts.ci.check_evidence_integrity import integrity_errors, known_invariant_ids

    ledger_doc = yaml.safe_load(LEDGER.read_text())
    violations = integrity_errors(ledger_doc, known_invariant_ids())
    if violations:
        raise SystemExit(
            "evidence-integrity FAIL — refusing to emit table on a contradictory ledger:\n  "
            + "\n  ".join(violations)
        )

    acc = entries()
    rows = []
    for e in acc:
        domain = domain_of(e)
        cls = e["classification"]
        tests = e.get("existing_tests") or []
        rows.append(
            {
                "contribution": e["id"],
                "domain": domain,
                "standard_anchor": TIER_ANCHOR.get(cls, "unclassified"),
                "claim_tier": cls,
                "file": e.get("file"),
                "test": tests,
                "gate": DOMAIN_GATE.get(domain, "tools/audit/neuro_symbolic_audit.py"),
                "falsifier": (e.get("falsifier") or "").strip(),
                "limitation": limitation_for(e),
                "replay": replay_for(tests),
                "promotion_allowed": bool(
                    cls == "OPERATIONAL"
                    and not (e.get("missing_tests") or [])
                    and (e.get("falsifier") or "").strip()
                    and tests
                    and any((e.get("inv_refs") or []))
                ),
            }
        )

    from collections import Counter

    table = {
        "schema": "academy-fellow/distinguished_evidence_table@v1",
        "source": ".claude/neuro/NEURO_OPERATIONALIZATION_LEDGER.yaml",
        "generated_by": "scripts/ci/gen_distinguished_evidence_table.py",
        "standards_referenced": [
            "Popper (1959) — falsifiability as demarcation.",
            "ACM Artifact Review & Badging v1.1 — Functional / Results-Reproduced tiers.",
            "FAIR (Wilkinson et al. 2016) — findable/accessible/interoperable/reusable.",
        ],
        "status_discipline": (
            "This table is disciplined against Distinguished-Professor-style standards of "
            "originality, evidence, reproducibility, and restraint. It is NOT a claim of a "
            "Distinguished-Professor-level result."
        ),
        "non_claims": [
            "No biological equivalence.",
            "No universal physics of markets; observers are not predictors.",
            "No alpha/profitability/edge.",
            "No B.wheel=0 (canonical packaging not achieved).",
            "Synthetic-only witnesses; no real L2 dataset/replay implied.",
        ],
        "summary": {
            "total": len(rows),
            "by_tier": dict(Counter(r["claim_tier"] for r in rows)),
            "promotion_allowed": sum(r["promotion_allowed"] for r in rows),
        },
        "rows": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(table, indent=2, ensure_ascii=False) + "\n")
    print(f"distinguished evidence table: {len(rows)} rows -> {OUT.relative_to(ROOT)}")
    print("by_tier:", table["summary"]["by_tier"])


if __name__ == "__main__":
    main()
