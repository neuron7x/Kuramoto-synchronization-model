# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Witnesses for the self-verifying cognitive-core meta-gate.

``scripts/ci/verify_cognitive_core.py`` composes the whole invariant centre into
ONE deterministic, content-addressed verdict: every blocking law witnessed
(positive + negative), the mutation floors well-formed, the cognitive core at a
1.0 code-mutation floor. The positive witness proves the verdict is GREEN and
reproducible (same SHA-256 across calls). The negative control proves the verdict
is non-vacuous: tampering with the catalog (stripping a negative control) makes
the underlying promotion gate FAIL, so the meta-gate cannot rubber-stamp.
"""
from __future__ import annotations

import copy

from core.physics.governance import (
    DEFAULT_CATALOG_PATH,
    load_catalog,
    promotion_gate,
)

from scripts.ci.verify_cognitive_core import ROOT, verify


def test_meta_gate_is_green_and_deterministic() -> None:
    """Positive witness: the composed verdict is GREEN and content-addressed reproducible."""
    first = verify()
    second = verify()

    assert first["verdict"] == "GREEN", (
        f"COGNITIVE-CORE META-GATE VIOLATED: composed verdict is {first['verdict']}, not GREEN. "
        f"failed checks={[k for k, v in first['checks'].items() if not v]}, "
        f"missing_positive={first['missing_positive_witness']}, "
        f"missing_negative={first['missing_negative_control']}."
    )
    assert all(first["checks"].values()), f"a meta-gate check failed: {first['checks']}"
    assert first["n_blocking"] >= 41, (
        f"COGNITIVE-CORE META-GATE: only {first['n_blocking']} blocking laws composed; "
        f"the invariant centre must cover the full executable spine."
    )
    assert first["cognitive_core_mutation_floor"] == 1.0, (
        "COGNITIVE-CORE META-GATE: cognitive_core.py is not at a 1.0 code-mutation floor."
    )
    # Content-addressed determinism: identical state -> identical signature.
    assert first["verdict_sha256"] == second["verdict_sha256"], (
        f"COGNITIVE-CORE META-GATE non-deterministic: {first['verdict_sha256']} != "
        f"{second['verdict_sha256']}; the verdict must be a pure function of contract state."
    )


def test_meta_gate_rejects_a_tampered_catalog() -> None:
    """Negative control: stripping a law's negative control makes the underlying gate FAIL.

    The meta-gate's GREEN hinges on ``promotion_gate`` passing. If a law loses its
    negative control, the gate must FAIL — proving the meta-gate cannot rubber-stamp
    an incompletely-witnessed catalog.
    """
    catalog = copy.deepcopy(load_catalog(DEFAULT_CATALOG_PATH))
    catalog["laws"][0]["negative_control"] = "tests/physics/test_ricci_kuramoto.py::does_not_exist"
    tampered = promotion_gate(catalog, ROOT, require_evidence=False)
    assert tampered["status"] == "FAIL", (
        f"COGNITIVE-CORE META-GATE VACUOUS: a catalog with a stripped negative control "
        f"still PASSED the promotion gate (status={tampered['status']}); the meta-gate "
        f"would rubber-stamp an incompletely-witnessed core."
    )

    # And the intact catalog passes (anchor: the tamper is what flips it, not a constant fail).
    intact = promotion_gate(load_catalog(DEFAULT_CATALOG_PATH), ROOT, require_evidence=False)
    assert intact["status"] == "PASS", "intact catalog must pass — else the control is not discriminating."
