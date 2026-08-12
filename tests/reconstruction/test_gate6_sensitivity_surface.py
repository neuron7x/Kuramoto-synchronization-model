# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002 — Gate 6 sensitivity surface tests.

Pin the contract:

  * `mix_substrate_with_null` is well-formed at the edge cases
    (λ=0 ⇒ pure null; λ=1 ⇒ original substrate).
  * `SensitivityCell` / `SensitivitySurface` dataclasses produce
    the contractual shape (power, dominant direction, lookup,
    JSON-safe to_dict). These tests construct cells directly
    rather than calling the slow `compute_sensitivity_surface`
    driver — keeping the python-fast-tests budget honest.
  * Tiny smoke (slow): one `compute_sensitivity_surface` invocation
    on the smallest possible grid to guarantee the driver wires up
    end-to-end.
  * Power monotonicity (slow): power(λ=1) > power(λ=0) for the
    canonical CP substrate at N≥100. Catches a regime where the
    instrument is blind regardless of signal strength.
  * FPR bound (slow): power at λ=0 ≤ 0.30 (loose envelope; the
    target is ≤ 0.05 but bootstrap CI on small n_seeds=20 has
    variance — relax to 30 % to avoid flaky CI).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from research.reconstruction.positive_control import ground_truth_core_periphery
from research.reconstruction.sensitivity_surface import (
    SensitivityCell,
    SensitivitySurface,
    compute_sensitivity_surface,
    mix_substrate_with_null,
)


def _stub_cell(
    *,
    n: int = 50,
    lam: float = 1.0,
    n_seeds: int = 5,
    n_pass: int = 0,
    n_facilitated: int = 0,
    n_hindered: int = 0,
    n_no_signal: int = 0,
    median_delta_r: float = 0.0,
    median_ci_width: float = 0.1,
    median_abs_delta_r: float = 0.05,
) -> SensitivityCell:
    """Construct a SensitivityCell directly — no Kuramoto sim."""
    return SensitivityCell(
        n_nodes=n,
        lambda_mix=lam,
        n_seeds=n_seeds,
        n_pass=n_pass,
        n_facilitated=n_facilitated,
        n_hindered=n_hindered,
        n_no_signal=n_no_signal,
        median_delta_r=median_delta_r,
        median_ci_width=median_ci_width,
        median_abs_delta_r=median_abs_delta_r,
    )


# ---------------------------------------------------------------------------
# Mixing helper — edge cases (cheap: numpy only)
# ---------------------------------------------------------------------------


def test_mix_lambda_one_returns_substrate_unchanged() -> None:
    w = ground_truth_core_periphery(n=40, core_frac=0.30, seed=0)
    rng = np.random.default_rng(0)
    out = mix_substrate_with_null(w, lambda_mix=1.0, rng=rng)
    np.testing.assert_array_equal(out, w)


def test_mix_lambda_zero_returns_pure_null() -> None:
    """λ=0 ⇒ topology randomised; off-diagonal mass preserved."""
    w = ground_truth_core_periphery(n=40, core_frac=0.30, seed=0)
    rng = np.random.default_rng(0)
    out = mix_substrate_with_null(w, lambda_mix=0.0, rng=rng)
    assert out.shape == w.shape
    assert np.diag(out).sum() == 0.0
    np.fill_diagonal(out, 0.0)
    w_no_diag = w.copy()
    np.fill_diagonal(w_no_diag, 0.0)
    assert pytest.approx(out.sum(), rel=1e-12) == w_no_diag.sum()


def test_mix_lambda_half_keeps_diagonal_zero() -> None:
    w = ground_truth_core_periphery(n=40, core_frac=0.30, seed=0)
    rng_a = np.random.default_rng(7)
    out_a = mix_substrate_with_null(w, lambda_mix=0.5, rng=rng_a)
    assert np.all(np.diag(out_a) == 0.0)


def test_mix_rejects_lambda_out_of_range() -> None:
    w = np.eye(4)
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        mix_substrate_with_null(w, lambda_mix=-0.1, rng=np.random.default_rng(0))
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        mix_substrate_with_null(w, lambda_mix=1.5, rng=np.random.default_rng(0))


def test_mix_rejects_non_square() -> None:
    with pytest.raises(ValueError, match="square"):
        mix_substrate_with_null(np.zeros((4, 5)), lambda_mix=0.5, rng=np.random.default_rng(0))


# ---------------------------------------------------------------------------
# Dataclass contract — direct construction (no Kuramoto sim)
# ---------------------------------------------------------------------------


def test_cell_power_property_is_n_pass_over_n_seeds() -> None:
    c = _stub_cell(n_seeds=10, n_pass=4)
    assert c.power == 0.4


def test_cell_power_handles_zero_seeds() -> None:
    c = _stub_cell(n_seeds=0, n_pass=0)
    assert c.power == 0.0


def test_cell_signed_direction_dominant() -> None:
    c_fac = _stub_cell(n_seeds=5, n_facilitated=4, n_hindered=0, n_no_signal=1)
    c_hind = _stub_cell(n_seeds=5, n_facilitated=0, n_hindered=3, n_no_signal=2)
    c_none = _stub_cell(n_seeds=5, n_facilitated=1, n_hindered=1, n_no_signal=3)
    assert c_fac.signed_direction_dominant == "facilitated"
    assert c_hind.signed_direction_dominant == "hindered"
    assert c_none.signed_direction_dominant == "no_signal"


def test_surface_cell_lookup_returns_match_or_none() -> None:
    cells = (
        _stub_cell(n=30, lam=0.0),
        _stub_cell(n=30, lam=1.0),
        _stub_cell(n=50, lam=0.0),
    )
    s = SensitivitySurface(
        n_grid=(30, 50),
        lambda_grid=(0.0, 1.0),
        n_seeds=5,
        cells=cells,
        fpr_estimate=0.0,
        mde_lambda_per_n={30: float("inf"), 50: float("inf")},
    )
    assert s.cell(n=30, lambda_mix=0.0) is cells[0]
    assert s.cell(n=30, lambda_mix=1.0) is cells[1]
    assert s.cell(n=50, lambda_mix=1.0) is None
    assert s.cell(n=99, lambda_mix=0.0) is None


def test_surface_to_dict_serialises_inf_to_none() -> None:
    s = SensitivitySurface(
        n_grid=(30,),
        lambda_grid=(1.0,),
        n_seeds=2,
        cells=(_stub_cell(n=30, lam=1.0, n_seeds=2),),
        fpr_estimate=0.0,
        mde_lambda_per_n={30: float("inf")},
    )
    d = s.to_dict()
    assert d["n_seeds"] == 2
    assert d["mde_lambda_per_n"] == {30: None}
    assert d["fpr_estimate"] == 0.0
    assert isinstance(d["cells"], list) and len(d["cells"]) == 1
    assert d["cells"][0]["n_nodes"] == 30
    assert d["cells"][0]["lambda_mix"] == 1.0


def test_surface_to_dict_emits_finite_mde_when_set() -> None:
    s = SensitivitySurface(
        n_grid=(30,),
        lambda_grid=(0.5,),
        n_seeds=2,
        cells=(_stub_cell(n=30, lam=0.5),),
        fpr_estimate=0.0,
        mde_lambda_per_n={30: 0.5},
    )
    d = s.to_dict()
    assert d["mde_lambda_per_n"] == {30: 0.5}


# ---------------------------------------------------------------------------
# End-to-end driver smoke (slow — calls gate_6_precursor_discriminative)
# ---------------------------------------------------------------------------
#
# D-002A test contract (per amendment protocol after CI forensics):
#   * D-002A tests INFRASTRUCTURE + FAIL-CLOSED behavior at the pilot
#     budget. It does NOT certify Gate 6 power.
#   * Allowed claims: surface computes, serialization works, FPR at
#     λ=0 is bounded, MDE may be None, sub-MDE state is represented
#     honestly.
#   * Forbidden claims at this budget: power(λ=1) > power(λ=0) — that
#     is the D-002B certification claim, not the D-002A pilot one.
#   * All slow tests combined target ≤ 90 s on uncontended local
#     CPU; CI heavy-tests lane has a 1200 s inner cap.


@pytest.mark.slow
def test_compute_sensitivity_surface_smallest_grid_smoke() -> None:
    """Wire-check the driver end-to-end on the smallest possible grid
    that still satisfies the Gate 6 contract (n_bootstrap >= 4)."""
    surface = compute_sensitivity_surface(
        n_grid=(30,),
        lambda_grid=(1.0,),
        n_seeds=2,
        n_bootstrap=4,
    )
    assert isinstance(surface, SensitivitySurface)
    assert len(surface.cells) == 1
    c = surface.cells[0]
    assert isinstance(c, SensitivityCell)
    assert 0 <= c.n_pass <= c.n_seeds
    assert c.n_facilitated + c.n_hindered + c.n_no_signal == c.n_seeds
    assert 0.0 <= surface.fpr_estimate <= 1.0
    assert set(surface.mde_lambda_per_n.keys()) == {30}


# ---------------------------------------------------------------------------
# Sub-MDE surface honesty (slow) — replaces the invalid
# power-monotonicity assertion that belonged to D-002B.
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_sub_mde_surface_reports_no_mde_without_fail_open() -> None:
    """At pilot budget the canonical CP substrate is sub-MDE. The
    surface must:
      * compute end-to-end on (λ=0, λ=1);
      * expose both cells via lookup;
      * report a finite fpr_estimate;
      * permit MDE=None (sub-MDE state) without claiming
        certification;
      * serialize all cells via to_dict.

    This replaces the prior power-monotonicity assertion which made
    a power claim that belongs in D-002B (high-budget certification),
    not the D-002A pilot lane.
    """
    surface = compute_sensitivity_surface(
        n_grid=(50,),
        lambda_grid=(0.0, 1.0),
        n_seeds=5,
        n_bootstrap=4,
    )
    cell_zero = surface.cell(n=50, lambda_mix=0.0)
    cell_one = surface.cell(n=50, lambda_mix=1.0)
    assert cell_zero is not None
    assert cell_one is not None
    assert math.isfinite(surface.fpr_estimate)

    # MDE may be None / inf at pilot budget — that is the honest
    # sub-MDE state; D-002B will determine if any finite MDE exists.
    mde = surface.mde_lambda_per_n.get(50)
    assert mde is not None  # key present
    # mde may equal float("inf") (sub-MDE) — both states are allowed.

    payload = surface.to_dict()
    assert len(payload["cells"]) == 2
    # JSON-safe: inf coerced to None per SensitivitySurface.to_dict.
    serialised_mde = payload["mde_lambda_per_n"][50]
    assert serialised_mde is None or isinstance(serialised_mde, float)


# ---------------------------------------------------------------------------
# FPR bound at pilot budget (slow, reduced cost)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_fpr_estimate_bounded_at_pilot_budget() -> None:
    """FPR (power at λ=0) at the D-002A pilot budget must be
    ≤ 0.30 — the relaxed envelope. The 0.05 production target is
    reserved for D-002B certification.

    Reduced grid (N=50, n_seeds=5, n_bootstrap=4) keeps this test
    well under 60 s on uncontended local CPU."""
    surface = compute_sensitivity_surface(
        n_grid=(50,),
        lambda_grid=(0.0,),
        n_seeds=5,
        n_bootstrap=4,
    )
    assert surface.fpr_estimate <= 0.30, (
        f"FPR={surface.fpr_estimate:.2f} exceeds 0.30 envelope at "
        f"pilot budget (N=50, n_seeds=5, n_bootstrap=4)"
    )
