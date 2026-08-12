# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002C C2.2 — Substrate generator tests.

Pins gates G6-G10 + G12-G14 for the substrate layer:

  G6   density ∈ [0.05, 0.15] for the sparse substrate family
  G7   K matrix symmetric at every time slice
  G8   no NaN / Inf in K
  G9   mean spectral radius / N ∈ [0.95, 1.05]
  G10  precursor injection produces a measurable Δ in K_F norm
       when lambda > 0; zero delta when lambda == 0
  G12  reproducible: same seed → identical realisation
  G13  monotone sanity: larger lambda → larger |Frobenius delta|
  G14  9 substrate × metric combos are pairable (registry sanity)

Strict scope: substrate construction tests only.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from research.systemic_risk.d002c_substrates import (
    ALL_SUBSTRATES,
    BLOCK_FRACTIONS,
    DENSITY_RANGE,
    PRE_EVENT_WINDOW,
    PRECURSOR_INJECTION_WINDOW,
    PRECURSOR_SPECTRAL_RANGE,
    SPECTRAL_RANGE,
    SUBSTRATE_BY_ID,
    T_HORIZON,
    BlockStructuredSubstrate,
    RicciFlowSubstrate,
    Substrate,
    SubstrateInvalid,
    SubstrateRealization,
    TemporalKtSubstrate,
    _enforce_calibration_gates,
)

# ---------------------------------------------------------------------------
# Canonical sweep grid (subset; full grid lives in the prereg YAML)
# ---------------------------------------------------------------------------
N_GRID = (50, 100, 200)
LAMBDA_GRID = (0.0, 0.05, 0.40, 1.0)
SUBSTRATES: tuple[Substrate, ...] = tuple(ALL_SUBSTRATES)
SUBSTRATE_IDS = tuple(s.id for s in SUBSTRATES)


# ---------------------------------------------------------------------------
# Registry sanity
# ---------------------------------------------------------------------------


def test_registry_has_three_substrates() -> None:
    assert len(ALL_SUBSTRATES) == 3
    assert SUBSTRATE_IDS == ("ricci_flow", "block_structured", "temporal_coupling")


def test_substrate_by_id_round_trip() -> None:
    for s in ALL_SUBSTRATES:
        assert SUBSTRATE_BY_ID[s.id].id == s.id


# ---------------------------------------------------------------------------
# G7+G8: shape + finiteness + symmetry at every time slice
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("substrate", SUBSTRATES, ids=SUBSTRATE_IDS)
@pytest.mark.parametrize("N", N_GRID)
@pytest.mark.parametrize("lambda_", LAMBDA_GRID)
def test_g7_g8_K_symmetric_finite_correct_shape(
    substrate: Substrate, N: int, lambda_: float
) -> None:
    r = substrate.realize(N=N, lambda_=lambda_, seed=42)
    assert r.K_baseline.shape == (T_HORIZON, N, N)
    assert r.K_precursor.shape == (T_HORIZON, N, N)
    for K in (r.K_baseline, r.K_precursor):
        assert np.all(np.isfinite(K))
        # symmetry at every slice (allow float jitter)
        for t in range(T_HORIZON):
            assert np.max(np.abs(K[t] - K[t].T)) < 1e-9


# ---------------------------------------------------------------------------
# G9: spectral radius / N ∈ [0.95, 1.05]
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("substrate", SUBSTRATES, ids=SUBSTRATE_IDS)
@pytest.mark.parametrize("N", N_GRID)
def test_g9_spectral_radius_calibrated(substrate: Substrate, N: int) -> None:
    r = substrate.realize(N=N, lambda_=0.0, seed=42)
    lo, hi = SPECTRAL_RANGE
    assert (
        lo <= r.spectral_radius_over_N <= hi
    ), f"{substrate.id} N={N}: spectral_radius/N = {r.spectral_radius_over_N:.4f}"


# ---------------------------------------------------------------------------
# G6: density in [0.05, 0.15] for the sparse substrate family (Ricci)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("N", N_GRID)
def test_g6_ricci_density_in_range(N: int) -> None:
    r = RicciFlowSubstrate().realize(N=N, lambda_=0.0, seed=42)
    d_lo, d_hi = DENSITY_RANGE
    assert (
        d_lo <= r.density <= d_hi
    ), f"ricci_flow N={N}: density = {r.density:.4f} outside [{d_lo}, {d_hi}]"


def test_block_substrate_density_full() -> None:
    """The block substrate is dense by construction; density gate N/A."""
    r = BlockStructuredSubstrate().realize(N=100, lambda_=0.0, seed=42)
    # fraction of non-zero off-diagonals — block matrix has nonzeros in
    # every off-diagonal entry by construction
    assert r.density == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# G10: precursor delta — strict zero at lambda=0, strict positive at lambda>0
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("substrate", SUBSTRATES, ids=SUBSTRATE_IDS)
def test_g10_lambda_zero_is_pure_baseline(substrate: Substrate) -> None:
    r = substrate.realize(N=100, lambda_=0.0, seed=42)
    assert r.precursor_frobenius_delta == 0.0
    # Strict: K_baseline == K_precursor element-wise
    assert np.array_equal(r.K_baseline, r.K_precursor)


@pytest.mark.parametrize("substrate", SUBSTRATES, ids=SUBSTRATE_IDS)
@pytest.mark.parametrize("lambda_", [0.05, 0.40, 1.0])
def test_g10_positive_lambda_yields_positive_delta(substrate: Substrate, lambda_: float) -> None:
    r = substrate.realize(N=100, lambda_=lambda_, seed=42)
    assert r.precursor_frobenius_delta > 0.0


# ---------------------------------------------------------------------------
# G12: bit-exact reproducibility on same seed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("substrate", SUBSTRATES, ids=SUBSTRATE_IDS)
def test_g12_same_seed_reproducible_bit_exact(substrate: Substrate) -> None:
    a = substrate.realize(N=100, lambda_=0.40, seed=7)
    b = substrate.realize(N=100, lambda_=0.40, seed=7)
    assert np.array_equal(a.K_baseline, b.K_baseline)
    assert np.array_equal(a.K_precursor, b.K_precursor)
    assert a.K_c == b.K_c
    assert a.density == b.density


def test_g12_different_seeds_yield_different_ricci() -> None:
    """Ricci substrate is the only one with stochastic ER topology;
    different seeds must give different K (else seed is not wired)."""
    a = RicciFlowSubstrate().realize(N=100, lambda_=0.0, seed=1)
    b = RicciFlowSubstrate().realize(N=100, lambda_=0.0, seed=2)
    assert not np.array_equal(a.K_baseline, b.K_baseline)


def test_block_substrate_seed_independent() -> None:
    """The block substrate is fully deterministic from (N, lambda_) — the
    seed must not change K. (If it does, that's a science bug — we'd be
    silently randomising the structural pattern.)"""
    a = BlockStructuredSubstrate().realize(N=100, lambda_=0.40, seed=1)
    b = BlockStructuredSubstrate().realize(N=100, lambda_=0.40, seed=999)
    assert np.array_equal(a.K_baseline, b.K_baseline)
    assert np.array_equal(a.K_precursor, b.K_precursor)


# ---------------------------------------------------------------------------
# G13: monotone sanity — larger lambda → larger |Frobenius delta|
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("substrate", SUBSTRATES, ids=SUBSTRATE_IDS)
def test_g13_delta_monotone_in_lambda(substrate: Substrate) -> None:
    d05 = substrate.realize(N=100, lambda_=0.05, seed=42).precursor_frobenius_delta
    d40 = substrate.realize(N=100, lambda_=0.40, seed=42).precursor_frobenius_delta
    d10 = substrate.realize(N=100, lambda_=1.00, seed=42).precursor_frobenius_delta
    assert 0.0 < d05 < d40 < d10


# ---------------------------------------------------------------------------
# G14: 9 substrate × metric combos pairable (registry sanity — metrics imported)
# ---------------------------------------------------------------------------


def test_g14_three_substrates_pairable_with_three_metrics() -> None:
    from research.systemic_risk.d002c_metrics import ALL_METRICS

    assert len(ALL_SUBSTRATES) == 3
    assert len(ALL_METRICS) == 3
    # All 9 combos are addressable by id
    pairs = [(s.id, m.id) for s in ALL_SUBSTRATES for m in ALL_METRICS]
    assert len(pairs) == 9
    assert len(set(pairs)) == 9


# ---------------------------------------------------------------------------
# Frozen-dataclass / mutation refusal
# ---------------------------------------------------------------------------


def test_substrate_realization_is_frozen() -> None:
    r = RicciFlowSubstrate().realize(N=50, lambda_=0.0, seed=42)
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.density = 0.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Precursor window confinement: outside PRECURSOR_INJECTION_WINDOW the
# baseline and precursor trajectories must be element-wise identical
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("substrate", SUBSTRATES, ids=SUBSTRATE_IDS)
def test_precursor_confined_to_injection_window(substrate: Substrate) -> None:
    r = substrate.realize(N=100, lambda_=1.0, seed=42)
    inject = set(PRECURSOR_INJECTION_WINDOW)
    for t in range(T_HORIZON):
        if t in inject:
            # Within injection window: precursor differs from baseline
            assert not np.array_equal(
                r.K_baseline[t], r.K_precursor[t]
            ), f"t={t} in injection window but baseline==precursor"
        else:
            assert np.array_equal(
                r.K_baseline[t], r.K_precursor[t]
            ), f"t={t} outside injection window but baseline!=precursor"


def test_precursor_injection_window_subset_of_pre_event_window() -> None:
    """The injection window must lie inside the pre-event observation window
    (otherwise the precursor lands on or past the event itself)."""
    assert set(PRECURSOR_INJECTION_WINDOW).issubset(set(PRE_EVENT_WINDOW))


# ---------------------------------------------------------------------------
# Contract: small-N and degenerate-param refusal
# ---------------------------------------------------------------------------


def test_ricci_rejects_N_too_small() -> None:
    with pytest.raises(SubstrateInvalid):
        RicciFlowSubstrate().realize(N=3, lambda_=0.0, seed=42)


def test_block_rejects_N_too_small() -> None:
    with pytest.raises(SubstrateInvalid):
        BlockStructuredSubstrate().realize(N=5, lambda_=0.0, seed=42)


def test_temporal_rejects_period_too_small() -> None:
    with pytest.raises(SubstrateInvalid):
        TemporalKtSubstrate(period_quarters=1).realize(N=100, lambda_=0.0, seed=42)


# ---------------------------------------------------------------------------
# Block structure: locked tier multipliers (sanity on the within-block pattern)
# ---------------------------------------------------------------------------


def test_block_structure_tier_multipliers_present() -> None:
    """The block substrate must have three distinct multiplier levels (1.5
    core/core, 1.0 core/mid, 0.5 mid/per, 0.2 per/per). After spectral
    calibration the absolute values change but the RATIOS must be
    preserved."""
    r = BlockStructuredSubstrate().realize(N=100, lambda_=0.0, seed=42)
    f_core, f_mid, _ = BLOCK_FRACTIONS
    n_core = max(1, int(round(f_core * 100)))
    n_mid = max(1, int(round(f_mid * 100)))
    K = r.K_baseline[0]
    # Core-core block off-diagonal mean
    core = K[:n_core, :n_core]
    off_core = core[np.triu_indices(n_core, k=1)]
    cm = K[:n_core, n_core : n_core + n_mid]
    pp = K[n_core + n_mid :, n_core + n_mid :]
    off_pp = pp[np.triu_indices(pp.shape[0], k=1)]
    mu_core_core = float(off_core.mean())
    mu_core_mid = float(cm.mean())
    mu_per_per = float(off_pp.mean())
    # Ratios must match 1.5 / 1.0 and 0.2 / 1.0 to within float jitter
    assert mu_core_core / mu_core_mid == pytest.approx(1.5, rel=1e-9)
    assert mu_per_per / mu_core_mid == pytest.approx(0.2, rel=1e-9)


# ---------------------------------------------------------------------------
# Temporal envelope: K(t) modulation amplitude (not over the full period
# the gate uses, but qualitative envelope check)
# ---------------------------------------------------------------------------


def test_temporal_envelope_modulates_K() -> None:
    r = TemporalKtSubstrate(period_quarters=4, amplitude=0.20).realize(N=100, lambda_=0.0, seed=42)
    # Some pair of time slices must differ by at least ~the modulation
    # amplitude in Frobenius norm
    fro_diffs = []
    for t in range(T_HORIZON):
        for s in range(t + 1, T_HORIZON):
            fro_diffs.append(np.linalg.norm(r.K_baseline[t] - r.K_baseline[s]))
    assert max(fro_diffs) > 0.0


def test_temporal_baseline_at_lambda_zero_is_identical_to_precursor() -> None:
    """Temporal-K substrate: λ=0 means the precursor field equals the
    baseline field at every slice — not just outside the injection
    window. (Otherwise the sinusoidal envelope itself would leak as a
    'precursor'.)"""
    r = TemporalKtSubstrate().realize(N=100, lambda_=0.0, seed=42)
    assert np.array_equal(r.K_baseline, r.K_precursor)


# ---------------------------------------------------------------------------
# SubstrateRealization basic invariants
# ---------------------------------------------------------------------------


def test_substrate_realization_carries_seed_and_lambda() -> None:
    r = RicciFlowSubstrate().realize(N=50, lambda_=0.40, seed=42)
    assert isinstance(r, SubstrateRealization)
    assert r.seed == 42
    assert r.lambda_ == pytest.approx(0.40)
    assert r.N == 50
    assert r.substrate_id == "ricci_flow"


# ---------------------------------------------------------------------------
# G9 precursor — Codex P1 regression (2026-05-11).
#
# The original implementation enforced the spectral gate ONLY on
# K_baseline; K_precursor was constructed but never spectrally
# validated. BlockStructuredSubstrate(..., lambda_=1.0) was producing
# ρ/N ≈ 1.052 — past the baseline gate hi of 1.05. The gate now
# applies a wider but bounded range to the precursor (
# PRECURSOR_SPECTRAL_RANGE = [0.95, 1.15]) reflecting that the precursor
# IS by design an amplification, while still refusing any pathological
# explosion that would push K past the comparable regime.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("substrate", SUBSTRATES, ids=SUBSTRATE_IDS)
@pytest.mark.parametrize("lambda_", [0.0, 0.05, 0.40, 1.0])
def test_g9_precursor_spectral_radius_in_range(substrate: Substrate, lambda_: float) -> None:
    """For every (substrate, λ) the PRECURSOR trajectory's mean spectral
    radius / N must lie inside :data:`PRECURSOR_SPECTRAL_RANGE`. This is
    the Codex P1 regression — without this gate a substrate at λ=1.0
    could silently push K outside the comparable regime and bias the
    downstream metric comparison."""
    r = substrate.realize(N=100, lambda_=lambda_, seed=42)
    p_lo, p_hi = PRECURSOR_SPECTRAL_RANGE
    assert (
        p_lo <= r.spectral_radius_over_N_precursor <= p_hi
    ), f"{substrate.id} λ={lambda_}: precursor ρ/N = {r.spectral_radius_over_N_precursor:.4f}"


def test_g9_precursor_spectral_radius_lambda_zero_equals_baseline() -> None:
    """At λ=0 the precursor field equals the baseline by construction —
    so the two spectral radii MUST be exactly equal (not just within
    each gate's range)."""
    for s in SUBSTRATES:
        r = s.realize(N=100, lambda_=0.0, seed=42)
        assert r.spectral_radius_over_N == pytest.approx(
            r.spectral_radius_over_N_precursor, abs=1e-12
        )


def test_g9_precursor_spectral_radius_monotone_in_lambda() -> None:
    """For every substrate, larger λ → larger precursor spectral radius
    (the precursor is constructed to amplify coupling). A non-monotone
    response would indicate the lift mechanism cancels with itself."""
    for s in SUBSTRATES:
        rho = [
            s.realize(N=100, lambda_=lam, seed=42).spectral_radius_over_N_precursor
            for lam in (0.0, 0.05, 0.40, 1.0)
        ]
        assert all(rho[i] <= rho[i + 1] for i in range(len(rho) - 1)), (
            s.id,
            rho,
        )


def test_g9_precursor_gate_refuses_out_of_range_synthetic() -> None:
    """Construct a synthetic (baseline, precursor) pair whose precursor
    sits *past* :data:`PRECURSOR_SPECTRAL_RANGE` and verify the gate
    refuses it. This is the fail-closed contract for any future
    substrate whose lift mechanism is mis-calibrated."""
    N = 8
    # Calibrated baseline: identity * 1.0 → ρ = 1.0, ρ/N = 0.125 (way
    # below baseline gate). We want a baseline INSIDE the range so the
    # baseline check passes, then a precursor OUTSIDE.
    K_baseline = np.broadcast_to(np.eye(N) * 1.0, (T_HORIZON, N, N)).copy()
    # Baseline ρ/N = 1.0/N = 0.125 — below the 0.95 floor. Need a
    # baseline whose ρ/N is inside [0.95, 1.05].
    K_baseline = np.broadcast_to(np.eye(N) * 1.0 * N, (T_HORIZON, N, N)).copy()
    # Precursor amplified by 30% (well past 1.15 cap)
    K_precursor = K_baseline.copy() * 1.30
    with pytest.raises(SubstrateInvalid, match="gate G9 precursor failed"):
        _enforce_calibration_gates(
            K_baseline=K_baseline,
            K_precursor=K_precursor,
            lambda_=1.0,
            density=None,
            substrate_id="synthetic",
            N=N,
        )
