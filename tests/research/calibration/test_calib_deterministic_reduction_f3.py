# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
r"""F3 — forcing functions for the deterministic-reduction harness.

These rails bind the F3 closure (audit PR #762, consolidation #759):

1. **Same-CPU bit-stability.** Under
   :func:`research.calibration.grid_kuramoto._deterministic.
   deterministic_reduction` the full ledger recomputes ``N = 5×``
   **bit-identical** (sha-stable on the provenance-stripped payload),
   and the structural property that makes cross-runner determinism
   *follow on a fixed CPU* (single-thread native pools) holds.

2. **Forward tolerance is derived, single-valued, and forcing.** The
   forward bound is ``1e-8``; it is strictly tighter than the legacy
   ``1e-6`` window; it strictly exceeds the *measured* worst-case
   single-thread cross-micro-kernel divergence (so it cannot be a
   flake); and a regression an order of magnitude beyond it is still
   detected (sharpness). A future silent re-loosening of the forward
   bound past the legacy window is a *reviewed, failing* event here.

3. **Regime split is explicit.** The legacy constants are unchanged
   (the historical sha-pinned ledgers were born under the OLD
   nondeterministic regime and are reproduced at the documented legacy
   ε, never recomputed); the forward constants are the tight ones. The
   two regimes are distinct objects, not one creeping window.

This file deliberately defines **no** ``_deep_close`` copy — the F1/F3
divergent-comparator forcing function
(``test_calib_lineage_forcing_functions.py::
test_deep_close_tolerance_is_pinned_single_valued_and_sharp``) pins the
governed comparator population at exactly two sites; F3 closes the
*root* (nondeterministic reduction), not by adding a third comparator.
"""

from __future__ import annotations

import hashlib
import io
import json
from contextlib import redirect_stderr
from typing import Any

import pytest

from research.calibration.grid_kuramoto import SimConfig, wscc_9_bus
from research.calibration.grid_kuramoto._deterministic import (
    FORWARD_ABS_TOL,
    FORWARD_REL_TOL,
    LEGACY_ABS_TOL,
    LEGACY_REL_TOL,
    OBSERVED_WORST_CROSS_KERNEL_REL,
    deterministic_reduction,
)
from research.calibration.grid_kuramoto.cg002 import build_cg002_ledger
from research.calibration.grid_kuramoto.run import build_ledger, build_r1_ledger

# Provenance fields legitimately move with the commit / environment and
# are excluded from the structural hash — exactly as the pre-existing
# ``_deep_close`` artifact tests exclude them.
_PROVENANCE_KEYS = frozenset({"branch_sha", "ledger_sha256"})


def _structural_sha(ledger: dict[str, Any]) -> str:
    """Provenance-stripped, sort-keyed sha256 of a ledger payload."""
    safe = {k: v for k, v in ledger.items() if k not in _PROVENANCE_KEYS}
    payload = json.dumps(safe, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def test_forward_tolerance_is_derived_single_valued_and_forcing() -> None:
    """The forward window is tighter-than-legacy, evidence-derived, sharp.

    Forcing function for the F3 generative mechanism (a reproduction
    window ~6 orders looser than the real noise floor masking a
    1e-9..1e-6 regression). Binds, with no peek:

    * the forward window strictly tighter than the legacy window
      (100× — a real tightening, not relabelling);
    * the forward window strictly *above* the measured worst-case
      single-thread cross-micro-kernel divergence (it is a derived
      bound on irreducible noise, not a flake-suppressor);
    * a regression an order of magnitude beyond the forward window is
      still rejected by a plain relative comparison (sharpness — a
      genuine post-data edit of plausible magnitude cannot be
      absorbed);
    * the legacy window is left exactly where it was (regime split:
      historical artifacts are NOT retroactively claimed bit-exact).
    """
    # Tighter than legacy — and by the audited factor (100×), so a
    # silent re-loosening toward the legacy window fails here.
    assert FORWARD_REL_TOL < LEGACY_REL_TOL
    assert LEGACY_REL_TOL / FORWARD_REL_TOL == pytest.approx(100.0, rel=1e-12)
    assert FORWARD_ABS_TOL == LEGACY_ABS_TOL  # abs floor unchanged (units)

    # The forward bound must strictly exceed the *measured* irreducible
    # cross-micro-kernel divergence, or it would flake by construction.
    assert OBSERVED_WORST_CROSS_KERNEL_REL < FORWARD_REL_TOL, (
        f"forward tol {FORWARD_REL_TOL:g} ≤ measured irreducible "
        f"divergence {OBSERVED_WORST_CROSS_KERNEL_REL:g} — the bound "
        f"is not above the noise floor it must bound"
    )
    # …but not absurdly above it: the safety margin is bounded so the
    # window cannot silently creep back toward the legacy 1e-6.
    margin = FORWARD_REL_TOL / OBSERVED_WORST_CROSS_KERNEL_REL
    assert 1.0 < margin < 50.0, (
        f"forward-tol safety margin {margin:.2f}× outside the audited "
        f"(1, 50) band — derivation drifted"
    )

    # Sharpness: a regression 10× beyond the forward window is detected
    # by a plain relative test (a real post-data edit cannot hide).
    base = 1.0
    regressed = base * (1.0 + 10.0 * FORWARD_REL_TOL) + 10.0 * FORWARD_ABS_TOL
    rel = abs(regressed - base) / abs(base)
    assert rel > FORWARD_REL_TOL, (
        "a 10×-forward-window regression is inside the forward window — "
        "the F3 silent-absorption failure mode would survive"
    )

    # Legacy window untouched (regime split, F2-amendment discipline).
    assert LEGACY_REL_TOL == 1e-6
    assert LEGACY_ABS_TOL == 1e-9


@pytest.mark.slow
def test_ledger_is_bit_identical_under_deterministic_reduction() -> None:
    """The full ledger recomputes bit-identical N=5× on a fixed CPU.

    Determinism proof for the F3 harness. Under
    :func:`deterministic_reduction` the native thread-pools are pinned
    to one thread, removing the thread-order component of FP
    nondeterminism. On a single CPU the *only* remaining variation
    would be the OpenBLAS micro-kernel — which is fixed for a fixed
    host — so the provenance-stripped structural sha256 of each of the
    three sha-pinned builders (CALIB-GRID-001, R1, CALIB-GRID-002) must
    be invariant across five independent recomputations.

    This is the structural property from which cross-runner behaviour
    *follows on a fixed CPU*; cross-*CPU* bit-identity is separately
    proven infeasible (RIP ``CALIB-F3``) and bounded by
    :data:`FORWARD_REL_TOL` instead.
    """
    builders = {
        "cg001": build_ledger,
        "r1": build_r1_ledger,
        "cg002": build_cg002_ledger,
    }
    sys = wscc_9_bus()
    cfg = SimConfig()

    with deterministic_reduction():
        for name, build in builders.items():
            hashes: list[str] = []
            for _ in range(5):
                buf = io.StringIO()
                with redirect_stderr(buf):  # silence the data-quality note
                    ledger = build(sys, cfg)
                hashes.append(_structural_sha(ledger))
            assert len(set(hashes)) == 1, (
                f"{name}: ledger is NOT bit-identical under the "
                f"deterministic-reduction harness on a fixed CPU "
                f"({len(set(hashes))} distinct sha256 over 5 builds) — "
                f"the determinism guarantee is broken"
            )
            # The structural property the cross-runner argument rests on:
            # the hash is a well-formed sha256 of a JSON-serialisable
            # provenance-stripped payload (no NaN/inf leaked into the
            # pinned structural fields would still hash, but the builders
            # also assert their own verdicts elsewhere).
            assert len(hashes[0]) == 64
            assert int(hashes[0], 16) >= 0


@pytest.mark.slow
def test_harness_does_not_change_the_mathematical_result() -> None:
    """Thread-pinning must not move a pinned metric beyond float-noise.

    Behaviour-preservation rail. If a pinned ledger metric moved by
    more than the forward window between the harnessed and the
    un-harnessed build *on the same CPU*, that would mean the harness
    changed the mathematics (or unmasked a latent bug the legacy 1e-6
    window was hiding) — an F3 *finding* to surface, never to absorb.
    Same-CPU same-kernel: the expected delta is exactly zero.
    """
    sys = wscc_9_bus()
    cfg = SimConfig()

    buf = io.StringIO()
    with redirect_stderr(buf):
        plain = build_r1_ledger(sys, cfg)
        with deterministic_reduction():
            harnessed = build_r1_ledger(sys, cfg)

    assert _structural_sha(plain) == _structural_sha(harnessed), (
        "deterministic_reduction changed the ledger on a fixed CPU — "
        "the harness is not behaviour-preserving (F3 finding: a pinned "
        "metric moved beyond float-noise; do not absorb, report)"
    )
