#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab); MIT
"""EBSVAP WP1 falsification set + metrics."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
s = importlib.util.spec_from_file_location("cc", REPO / "src/ebsvap/claim_compiler.py")
cc = importlib.util.module_from_spec(s)
sys.modules["cc"] = cc
s.loader.exec_module(cc)
C = cc.Claim

# seeded set: 7 critical overclaims (must REJECT) + 3 valid controls (must ADMIT)
overclaims = [
    C("O1", "the edge is empirically validated", "EMPIRICAL", {}),  # no data
    C("O2", "the reviewer is calibrated", "PROBABILISTIC", {}),  # no calibration
    C("O3", "X causes Y", "CAUSAL", {"data": "correlation"}),  # no intervention
    C("O4", "the method generalizes", "GENERALIZATION", {"data": "iid_only"}),  # iid only
    C(
        "O5",
        "independently verified",
        "EMPIRICAL",
        {"data": 1, "source": "impl", "independent_source": "impl"},
    ),
    C("O6", "the system is safe", "SAFETY", {"unit_tests_only": True}),  # unit tests only
    C("O7", "the stopping rule is optimal", "PERFORMANCE", {"data": 1}),  # 'optimal' no proof
]
valid = [
    C("V1", "coverage established under i.i.d.", "EMPIRICAL", {"data": 1, "raw_log": 1}),
    C(
        "V2",
        "the marginal is not coverable under dependence (counterexample)",
        "EMPIRICAL",
        {"data": 1},
    ),
    C(
        "V3",
        "kill-switch fails closed on corrupt state",
        "SAFETY",
        {"data": 1, "unit_tests_only": False},
    ),
]
res_over = [cc.compile_claim(c) for c in overclaims]
res_val = [cc.compile_claim(c) for c in valid]
crit_recall = sum(1 for r in res_over if r["status"] == "REJECT") / len(res_over)
false_rej = sum(1 for r in res_val if r["status"] == "REJECT") / len(res_val)
out = {
    "task": "WP1 atomic claim compiler",
    "critical_unsupported_claim_recall": crit_recall,
    "valid_claim_false_rejection_rate": false_rej,
    "overclaims": [{**r, "seeded": "REJECT"} for r in res_over],
    "valid_controls": [{**r, "seeded": "ADMIT"} for r in res_val],
    "pass": crit_recall == 1.0 and false_rej == 0.0,
    "verdict": (
        "CLAIM_COMPILER_PASS"
        if (crit_recall == 1.0 and false_rej == 0.0)
        else "CLAIM_COMPILER_FAIL"
    ),
}
(REPO / "artifacts/ebsvap/WP1_RESULTS.json").write_text(json.dumps(out, indent=2) + "\n")
for r in res_over:
    print(f"  {r['claim_id']} -> {r['status']} ({r['reason'][:50]})")
for r in res_val:
    print(f"  {r['claim_id']} -> {r['status']}")
print(f"recall={crit_recall} false_rej={false_rej} VERDICT: {out['verdict']}")
sys.exit(0 if out["pass"] else 1)
