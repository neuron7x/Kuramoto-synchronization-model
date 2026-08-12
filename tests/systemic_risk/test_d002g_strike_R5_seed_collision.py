# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Strike R5 — Phase 0a must hold for ALL 50 paired seeds, not seed=42 alone.

Attack
------
``check_phase_0a`` (d002g_phase0_verification.py) only exercises a single
``base_seed`` per cell. Phase 0b sweeps 50 seeds; if any of those 50
seeds collides under the arithmetic offset ``null_seed = base_seed +
NULL_SEED_OFFSET``, the M1 null silently reverts to bit-identical at
the colliding seed without Phase 0a noticing.

This test sweeps all 50 seeds and asserts:
  (a) ``not np.array_equal(K_p, K_n)`` for every seed,
  (b) ``‖K_p - K_n‖_F > N * eps`` (eps = 1e-12) for every seed.

Substrate scope
---------------
Stock ``ricci_flow`` is the only seed-sensitive substrate at lambda=0;
``block_structured`` / ``temporal_coupling`` are seed-deterministic at
lambda=0 (the substrate spec deliberately deletes the seed argument
there — they are M1-INELIGIBLE by design and pass through the prereg
§4 fallback to M2). This test exercises ricci_flow only — the
"all 50 seeds" R5 claim is meaningful exactly where M1 is eligible.
"""

from __future__ import annotations

import numpy as np
import pytest

from research.systemic_risk.d002c_substrates import SUBSTRATE_BY_ID
from research.systemic_risk.d002g_null_mechanisms import (
    BitIdenticalNullError,
    realize_null,
)

# 50-seed sweep on ricci_flow — gate behind `slow` so python-fast-tests
# stays under its 20-min cap.
pytestmark = pytest.mark.slow

SEED_SENSITIVE_SUBSTRATES: tuple[str, ...] = ("ricci_flow",)


@pytest.mark.parametrize("substrate_id", SEED_SENSITIVE_SUBSTRATES)
@pytest.mark.parametrize("N", [20, 50])
def test_R5_phase0a_holds_for_all_50_seeds(substrate_id: str, N: int) -> None:
    """For every seed in 0..49, M1 K_null must be Frobenius-distinct from K_p."""
    sub = SUBSTRATE_BY_ID[substrate_id]
    eps = 1e-12
    for base_seed in range(50):
        precursor_real = sub.realize(N=N, lambda_=0.0, seed=base_seed)
        K_p = np.asarray(precursor_real.K_baseline[0], dtype=np.float64)
        try:
            null_real = realize_null(
                sub,
                strategy="M1_INDEPENDENT_SEED",
                base_seed=base_seed,
                N=N,
                lambda_value=0.0,
            )
        except BitIdenticalNullError as exc:
            raise AssertionError(
                f"R5 VIOLATED: substrate={substrate_id!r} N={N} seed={base_seed} "
                f"produced bit-identical M1 null under offset arithmetic. "
                f"Phase 0a sweeps only seed=42 — this seed would have escaped. "
                f"Detail: {exc}"
            ) from exc
        K_n = np.asarray(null_real.K_baseline, dtype=np.float64)
        assert not np.array_equal(K_p, K_n), (
            f"R5 VIOLATED: substrate={substrate_id!r} N={N} seed={base_seed} "
            "→ np.array_equal(K_p, K_n) is True (silent collision under "
            "arithmetic offset)"
        )
        frob = float(np.linalg.norm(K_p - K_n))
        assert frob > N * eps, (
            f"R5 VIOLATED: substrate={substrate_id!r} N={N} seed={base_seed} "
            f"→ ‖K_p - K_n‖_F = {frob:.3e} ≤ N*eps = {N * eps:.3e} "
            "(spectrally indistinguishable null)"
        )
