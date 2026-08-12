# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Witnesses for cognitive_core_runtime_enforcement — the value function with teeth.

``require_admissible`` is the live wiring of the cognitive core into control: an
actuation path calls it and may only proceed if the snapshot lies inside the
invariant manifold. A GO snapshot passes through with its verdict; any NO_GO — a
fired gate, or an insufficient/empty snapshot — raises ``InadmissibleStateError``
fail-closed, with the binding constraint attached. There is no silent path to
action outside the manifold.

Positive witness: an in-manifold snapshot returns its GO verdict (and a custom
core is honoured). Negative control: a violated snapshot and an empty snapshot
both raise, the error carries the verdict and names the binding constraint, and
the default core enforces the same boundary.
"""
from __future__ import annotations

import math

import pytest

from core.physics.cognitive_core import (
    DEFAULT_GATES,
    CognitiveCore,
    Decision,
    InadmissibleStateError,
    Status,
    require_admissible,
)

_NOMINAL: dict[str, object] = {
    "order_parameter_R": 0.5,
    "z_abs": 0.4,
    "ollivier_kappa": 0.2,
    "gamma": 1.5,
    "serotonin_level": 0.3,
    "gaba_gate": 0.8,
    "dopamine_signal": 0.5,
    "kelly_fraction": 0.25,
    "free_energy_components": (1.0, 0.5, 0.2),
}


def test_require_admissible_passes_in_manifold_state() -> None:
    """Positive witness: a GO snapshot passes the runtime gate and returns its verdict."""
    verdict = require_admissible(_NOMINAL)
    assert verdict.decision is Decision.GO and verdict.status is Status.ADMISSIBLE, (
        f"COGNITIVE-CORE RUNTIME-GATE VIOLATED: an in-manifold snapshot was not "
        f"admitted (decision={verdict.decision}, status={verdict.status}, "
        f"violations={verdict.violations}); actuation must be allowed inside the manifold."
    )
    # A custom core is honoured, not silently replaced by the default singleton.
    # Build a restricted core that gates ONLY INV-K1, then feed a snapshot the
    # restricted core ADMITS but the default core REJECTS (bad ollivier_kappa).
    # If the gate used the default core instead of the passed one, this raises.
    k1_only = CognitiveCore(
        gates=tuple(g for g in DEFAULT_GATES if g.field_name == "order_parameter_R")
    )
    discriminating = {"order_parameter_R": 0.5, "ollivier_kappa": 2.0}  # RC1-violating
    restricted = require_admissible(discriminating, core=k1_only)
    assert restricted.decision is Decision.GO, (
        "COGNITIVE-CORE RUNTIME-GATE VIOLATED: the passed (restricted) core was not "
        "honoured — a snapshot it admits was rejected, so the gate used the wrong core."
    )
    with pytest.raises(InadmissibleStateError):
        require_admissible(discriminating)  # default core DOES gate INV-RC1 -> refuse


def test_require_admissible_refuses_out_of_manifold_and_empty_states() -> None:
    """Negative control: violated / empty snapshots raise fail-closed with the constraint.

    The runtime gate must PREVENT the action, not merely report it. A single
    invariant violation raises with that invariant as the binding constraint; an
    empty snapshot (no evidence) raises (no vacuous actuation); a non-finite field
    raises (fail-closed). The raised error carries the full verdict.
    """
    bad = dict(_NOMINAL)
    bad["order_parameter_R"] = 1.5  # INV-K1 out of [0,1]
    with pytest.raises(InadmissibleStateError) as exc:
        require_admissible(bad)
    assert exc.value.verdict.decision is Decision.NO_GO, "raised error must carry the NO_GO verdict"
    assert exc.value.verdict.binding_constraint == "INV-K1", (
        f"COGNITIVE-CORE RUNTIME-GATE VIOLATED: binding_constraint="
        f"{exc.value.verdict.binding_constraint!r}, expected 'INV-K1'."
    )
    # The raised message must surface the binding constraint in its dedicated field
    # (not merely inside the violations list), so an operator sees WHICH gate fired.
    assert "binding_constraint=INV-K1" in str(exc.value), (
        f"COGNITIVE-CORE RUNTIME-GATE VIOLATED: error message does not surface the "
        f"binding constraint as 'binding_constraint=INV-K1': {exc.value!s}"
    )

    # Empty snapshot: no applicable gate -> INSUFFICIENT -> refuse (no vacuous actuation).
    with pytest.raises(InadmissibleStateError) as exc_empty:
        require_admissible({})
    assert exc_empty.value.verdict.status is Status.INSUFFICIENT, (
        f"COGNITIVE-CORE RUNTIME-GATE VIOLATED: empty snapshot status="
        f"{exc_empty.value.verdict.status}; an evidence-free state must not actuate."
    )

    # Non-finite field is fail-closed.
    nonfinite = dict(_NOMINAL)
    nonfinite["gamma"] = math.nan
    with pytest.raises(InadmissibleStateError) as exc_nan:
        require_admissible(nonfinite)
    assert "INV-DRO2" in exc_nan.value.verdict.violations, (
        f"COGNITIVE-CORE RUNTIME-GATE VIOLATED: non-finite gamma not failed closed "
        f"(violations={exc_nan.value.verdict.violations})."
    )

    # A GO snapshot does NOT raise (the gate is not trigger-happy).
    assert require_admissible(_NOMINAL).admissible is True
