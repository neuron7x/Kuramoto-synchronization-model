# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Architectural forcing function for the swing coupling-estimator stack.

``core.kuramoto.coupling_estimator`` was an open-loop universal sink:
every CALIB-GRID lineage bolted another symmetric-joint estimation path
(``estimate_swing_coupling`` R1, then ``estimate_swing_coupling_integral``
CALIB-GRID-002) onto the module with its global-design assembly inlined
into the public function — 521 → 1322 LOC, +154 % over five lineages,
monotonic, with no strategy/boundary capping growth. PR #759 extracted
the shared solve tail (``_solve_symmetric_joint``); this refactor
extracted the path-specific *design assembly* into registered
:class:`SwingDesignStrategy` objects and turned the public functions
into thin dispatchers.

This module is the missing module-scale negative-feedback term (it
mirrors the lineage-scale forcing functions added in #762). It is
strictly pure-additive — no production formula, no frozen artifact, no
gate/threshold/seed and no pre-existing test is touched. Each test fails
closed the moment a future symmetric-joint estimation path is added
*outside* the registry or perturbs a path's numerics:

* ``test_every_symmetric_joint_path_dispatches_through_registry`` — the
  set of public symmetric-joint swing entry points equals the set of
  registered strategies routed by the single dispatcher. A lineage that
  inlines a third ``estimate_swing_coupling_*`` symmetric-joint design
  instead of registering a strategy fails this test (the structural cap
  on the monotonic accretion).
* ``test_dispatcher_core_is_path_independent`` — the one dispatcher
  ``_dispatch_swing`` mentions no path-specific symbol; new paths cannot
  be wired by editing it.
* ``test_strategy_registry_is_frozen_and_fail_closed`` — strategies are
  frozen, the registry rejects a duplicate key (no silent shadowing of
  an audited path), and the public view is read-only.
* ``test_golden_vectors_algorithm_preserving`` — every estimation
  path's ``K̂`` / ``ω̂`` / ``P̂`` / identifiability score / PE diagnostic
  and every prox operator reproduce the values captured on the parent
  sha (65666072), proving the extraction is algorithm-preserving.

  Determinism note (root-fix for a confirmed cross-runner flake). The
  earlier revision compared ``sha256(arr.tobytes())`` against byte-for-
  byte golden hashes. Byte equality is *too strict a verdict*: it fires
  not only on a genuine algorithm change but also on environment-only
  float noise. ``numpy``/``scipy`` here link OpenBLAS built with
  ``DYNAMIC_ARCH`` + multi-threaded reductions, so the last bit of an
  SVD / lstsq / iterative-prox result depends on (a) the detected CPU
  microkernel (Haswell vs Skylake vs Zen ⇒ different FMA/vectorisation
  order) and (b) the thread count of the runner. Those are *not*
  algorithm changes, yet they flip a byte hash — a false positive. The
  repo has already filed cross-environment BLAS bit-determinism as
  infeasible. This test therefore (1) pins ``threadpool_limits(1)`` to
  remove the intra-run thread-reduction component of the noise and
  (2) compares the actual numeric arrays with a *physically separated*
  tolerance: ``rtol=1e-9, atol=1e-12``. Every quantity here is O(1), so
  the band sits ~10⁶× above the worst plausible cross-arch last-bit
  noise (≲1e-12 relative on these well-conditioned O(1) solves) and
  ~10⁷× below any genuine refactor breach (a wrong design row, dropped
  term, sign error or wrong stencil moves a result by ≥1e-2). The gate
  thus still fails closed on a real algorithm change — proven by
  ``test_golden_gate_catches_real_drift`` below — while no longer
  flaking on environment float noise. Goldens were regenerated under
  ``threadpool_limits(1)`` and verified stable across ≥3 runs; the
  underlying values are unchanged from sha 65666072 (the refactor is
  bit-identical on this build), only the *comparison* moved from byte
  hash to separated tolerance.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from core.kuramoto.contracts import PhaseMatrix
from core.kuramoto.coupling_estimator import (
    CouplingEstimationConfig,
    CouplingEstimator,
    SwingDesign,
    SwingDesignStrategy,
    complementary_pairs_stability,
    estimate_coupling,
    estimate_swing_coupling,
    estimate_swing_coupling_integral,
    mcp_prox,
    scad_prox,
    soft_threshold,
    swing_strategy_registry,
)

_MODULE = Path(__file__).resolve().parents[3] / "core" / "kuramoto" / "coupling_estimator.py"


# ---------------------------------------------------------------------------
# Structural cap: every symmetric-joint path goes through the registry
# ---------------------------------------------------------------------------


def test_every_symmetric_joint_path_dispatches_through_registry() -> None:
    """Symmetric-joint estimation paths == registered strategies.

    The two public symmetric-joint swing entry points (the differential
    ``estimate_swing_coupling`` with ``symmetric=True`` and the
    weak/integral ``estimate_swing_coupling_integral``) each route
    through ``_dispatch_swing`` with a registry key, and the registry
    holds exactly those keys. A future lineage that adds a third
    symmetric-joint design inline — instead of registering a strategy —
    breaks this equality and fails closed.
    """
    registry = swing_strategy_registry()
    assert set(registry) == {"differential_symmetric", "integral_weak_form"}, (
        "registered swing strategy key set drifted — a new symmetric-joint "
        "estimation path must register a SwingDesignStrategy, not inline its "
        "design assembly into the dispatcher/public function"
    )

    # encoding pinned: coupling_estimator.py carries β/θ/λ/κ glyphs; a
    # locale-default read crashes under an ASCII CI locale (UnicodeDecodeError).
    tree = ast.parse(_MODULE.read_text(encoding="utf-8"))
    dispatched_keys: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_dispatch_swing"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            dispatched_keys.add(node.args[0].value)
    assert dispatched_keys == set(registry), (
        f"dispatched keys {sorted(dispatched_keys)} != registered "
        f"{sorted(registry)} — a symmetric-joint path bypassed the registry "
        "or a registered strategy is unreachable (orphaned accretion)"
    )

    # Every registered strategy satisfies the frozen contract.
    for key, strat in registry.items():
        assert isinstance(strat, SwingDesignStrategy)
        assert strat.key == key


def test_dispatcher_core_is_path_independent() -> None:
    """The single dispatcher mentions no path-specific estimator symbol.

    ``_dispatch_swing`` selects a strategy by key and runs the shared
    tail; it must not name a Savitzky–Golay / weak-form / stencil symbol
    (that would mean a path was wired by editing the dispatcher rather
    than by registering a strategy).
    """
    import core.kuramoto.coupling_estimator as ce

    body = inspect.getsource(ce._dispatch_swing)
    forbidden = ("savgol", "_test_function_stencil", "bump_order", "trapezoid", "unwrap")
    leaked = [tok for tok in forbidden if tok in body]
    assert not leaked, (
        f"_dispatch_swing leaked path-specific symbols {leaked} — the "
        "dispatcher core must stay path-independent so new paths require "
        "strategy registration, not a dispatcher edit"
    )


def test_strategy_registry_is_frozen_and_fail_closed() -> None:
    """Strategies are frozen, the view is read-only, dup keys rejected."""
    import core.kuramoto.coupling_estimator as ce

    registry = swing_strategy_registry()
    strat = next(iter(registry.values()))
    # Frozen dataclass: attribute assignment is blocked.
    try:
        strat.key = "mutated"  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - defensive
        raise AssertionError("swing strategy must be frozen (no attr set)")
    # Read-only public view.
    try:
        registry["x"] = strat  # type: ignore[index]
    except TypeError:
        pass
    else:  # pragma: no cover - defensive
        raise AssertionError("swing_strategy_registry() view must be read-only")
    # Duplicate-key registration is fail-closed (no silent shadow).
    existing = next(iter(registry.values()))
    try:
        ce._register_swing_strategy(existing)
    except ValueError:
        pass
    else:  # pragma: no cover - defensive
        raise AssertionError("duplicate strategy key must fail closed")

    # SwingDesign is a frozen contract carrying only the assembly output.
    sd = SwingDesign(
        design=np.zeros((2, 2), dtype=np.float64),
        target=np.zeros(2, dtype=np.float64),
        edges=[(0, 1)],
        n_edge=1,
    )
    try:
        sd.n_edge = 2  # type: ignore[misc]
    except AttributeError:
        pass
    else:  # pragma: no cover - defensive
        raise AssertionError("SwingDesign must be frozen")


# ---------------------------------------------------------------------------
# Algorithm-preserving extraction: golden vectors pinned to parent sha
# ---------------------------------------------------------------------------


# Physically-separated comparison band (see module docstring). O(1)
# quantities ⇒ rtol dominates; atol guards the few exact-zero entries.
# Floor (BLAS cross-arch last-bit noise ≲1e-12 rel) ≪ rtol ≪ ceiling
# (a genuine refactor breach ≥1e-2). assert_allclose fails the test if
# ANY element drifts past the band — it is not a soft check.
_RTOL = 1e-9
_ATOL = 1e-12


def _first_order_pm() -> tuple[PhaseMatrix, np.ndarray]:
    rng = np.random.default_rng(42)
    n, t_len, dt = 6, 1500, 0.05
    k_true = np.zeros((n, n))
    k_true[0, 1] = 1.8
    k_true[1, 0] = 1.5
    k_true[2, 3] = -1.2
    k_true[4, 5] = 2.0
    omega = rng.uniform(0.3, 0.7, n)
    theta = np.zeros((t_len, n))
    theta[0] = rng.uniform(0.0, 2 * np.pi, n)
    for t in range(1, t_len):
        di = theta[t - 1, None, :] - theta[t - 1, :, None]
        theta[t] = (
            theta[t - 1]
            + dt * (omega + np.sum(k_true * np.sin(di), axis=1))
            + 0.05 * rng.standard_normal(n) * np.sqrt(dt)
        )
    theta = np.mod(theta, 2 * np.pi)
    pm = PhaseMatrix(
        theta=theta,
        timestamps=np.arange(t_len, dtype=np.float64) * dt,
        asset_ids=tuple(f"x{i}" for i in range(n)),
        extraction_method="hilbert",
        frequency_band=(0.01, 1.0),
    )
    return pm, theta


def _swing_pm() -> tuple[PhaseMatrix, np.ndarray, np.ndarray]:
    k = np.array([[0.0, 0.9, 0.5], [0.9, 0.0, 0.7], [0.5, 0.7, 0.0]])
    p = np.array([0.6, -0.1, -0.5]) - np.mean([0.6, -0.1, -0.5])
    m = np.array([0.4, 0.5, 0.3])
    d = np.array([0.25, 0.3, 0.2])
    rng = np.random.default_rng(11)
    th0 = rng.uniform(-0.8, 0.8, 3)
    th0 -= th0.mean()
    nn, dt, n = 3, 0.005, 4000
    thr = th0.astype(np.float64).copy()
    v = np.zeros(nn)
    traj = np.empty((n + 1, nn))
    traj[0] = thr

    def accel(x: np.ndarray, w: np.ndarray) -> np.ndarray:
        di = x[:, None] - x[None, :]
        return np.asarray((p - (k * np.sin(di)).sum(1) - d * w) / m, dtype=np.float64)

    for t in range(n):
        a1 = accel(thr, v)
        a2 = accel(thr + 0.5 * dt * v, v + 0.5 * dt * a1)
        a3 = accel(thr + 0.5 * dt * (v + 0.5 * dt * a1), v + 0.5 * dt * a2)
        a4 = accel(thr + dt * (v + 0.5 * dt * a2), v + dt * a3)
        thr = thr + dt * v + (dt * dt / 6.0) * (a1 + 2 * a2 + 2 * a3)
        v = v + (dt / 6.0) * (a1 + 2 * a2 + 2 * a3 + a4)
        traj[t + 1] = thr
    w = np.mod(traj, 2 * np.pi)
    w = np.clip(w, 0.0, np.nextafter(2 * np.pi, 0.0))
    pm = PhaseMatrix(
        theta=w,
        timestamps=np.arange(w.shape[0], dtype=np.float64) * dt,
        asset_ids=("a", "b", "c"),
        extraction_method="hilbert",
        frequency_band=(1e-6, 0.5),
    )
    return pm, m, d


# Golden vectors. Underlying values captured on the parent sha 65666072
# (pre-refactor); regenerated under ``threadpool_limits(1)`` and verified
# stable across ≥3 runs. The refactor is bit-identical on the reference
# build, so these are the same numbers as before — only the comparison
# moved from a byte hash to the separated tolerance ``_RTOL``/``_ATOL``
# (see module docstring for the root-cause / flake analysis). Array
# goldens carry full float64 repr precision so a within-band match is a
# genuine reproduction, not a coarse approximation.
#
# NOTE (fix/coupling-estimator-median-contract): the ``first_order_stab_K``
# and ``cps_K_median`` goldens were re-frozen when
# ``complementary_pairs_stability`` was corrected to return the true MEDIAN
# of the pooled non-zero per-edge estimates (its documented contract and the
# ``K_median`` name) instead of the arithmetic MEAN it previously computed
# via ``weight_sum / weight_n``. The old goldens ENCODED that mean bug
# (e.g. edge [0,1] 0.3337… mean → 0.3134… median), so they are updated to the
# contracted statistic. Every other path is untouched — the stability-score
# goldens (``first_order_stab_scores`` / ``cps_stability``) are unchanged
# because selection probability never depended on the weight aggregation.
_GOLDEN_ARRAYS: dict[str, np.ndarray] = {
    "first_order_mcp_K": np.array(
        [
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, -0.674062254534137, 0.0, 0.0],
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.7803269007960915],
            [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        ]
    ),
    "first_order_stab_K": np.array(
        [
            [0.0, 0.3134276523323715, 0.0, 0.0, -0.011995775857773193, 0.01121196130711508],
            [
                -0.17576958030518114,
                0.0,
                -0.04221085111404079,
                0.0,
                0.1356051491263263,
                -0.031181124401335032,
            ],
            [0.0, 0.0, 0.0, -1.131497505723127, -0.41267214407673014, 0.3741990227964429],
            [0.022456070215847286, 0.0, 0.17895892857715595, 0.0, 0.01884556938981613, 0.0],
            [0.09442110626740136, 0.0, 0.0, -0.1587599222349002, 0.0, 1.5940773810479958],
            [
                0.0,
                0.002190539872401141,
                0.011513286362337156,
                0.06131027177503477,
                -0.05456143619366542,
                0.0,
            ],
        ]
    ),
    "first_order_stab_scores": np.array(
        [
            [0.0, 0.875, 0.375, 0.375, 0.5, 0.5],
            [0.75, 0.0, 0.625, 0.375, 0.5, 0.75],
            [0.375, 0.375, 0.0, 1.0, 1.0, 1.0],
            [0.625, 0.25, 0.875, 0.0, 0.625, 0.375],
            [1.0, 0.375, 0.375, 1.0, 0.0, 1.0],
            [0.375, 0.625, 0.625, 0.5, 0.875, 0.0],
        ]
    ),
    "cps_K_median": np.array(
        [
            [
                0.0,
                0.3134276523323715,
                -0.031223100845418364,
                -0.013824320760149795,
                -0.011995775857773193,
                0.01121196130711508,
            ],
            [
                -0.17576958030518114,
                0.0,
                -0.04221085111404079,
                -0.0034101947577266883,
                0.1356051491263263,
                -0.031181124401335032,
            ],
            [
                -0.027950851581587513,
                0.045415693941552565,
                0.0,
                -1.131497505723127,
                -0.41267214407673014,
                0.3741990227964429,
            ],
            [
                0.022456070215847286,
                0.04289850229685784,
                0.17895892857715595,
                0.0,
                0.01884556938981613,
                0.05348899269934553,
            ],
            [
                0.09442110626740136,
                0.08847671373736674,
                -0.7434883150981524,
                -0.1587599222349002,
                0.0,
                1.5940773810479958,
            ],
            [
                0.01697287466157524,
                0.002190539872401141,
                0.011513286362337156,
                0.06131027177503477,
                -0.05456143619366542,
                0.0,
            ],
        ]
    ),
    "cps_stability": np.array(
        [
            [0.0, 0.875, 0.375, 0.375, 0.5, 0.5],
            [0.75, 0.0, 0.625, 0.375, 0.5, 0.75],
            [0.375, 0.375, 0.0, 1.0, 1.0, 1.0],
            [0.625, 0.25, 0.875, 0.0, 0.625, 0.375],
            [1.0, 0.375, 0.375, 1.0, 0.0, 1.0],
            [0.375, 0.625, 0.625, 0.5, 0.875, 0.0],
        ]
    ),
    "mcp_prox": np.array([-1.7999999999999998, 0.0, 0.0, 0.0, 1.2, 4.0]),
    "scad_prox": np.array([-1.6136363636363635, -0.0, 0.0, 0.0, 1.0, 4.0]),
    "soft_threshold": np.array([-1.8, -0.09999999999999998, 0.0, 0.09999999999999998, 1.3, 3.8]),
    "swing_sym_K": np.array(
        [
            [0.0, 0.9019333478526244, 0.4970868336621068],
            [0.9019333478526244, 0.0, 0.7047115365209683],
            [0.4970868336621068, 0.7047115365209683, 0.0],
        ]
    ),
    "swing_sym_P": np.array([0.598846754398815, -0.09922948373250914, -0.49961727060982025]),
    "swing_sym_omega": np.array([2.39538701759526, -0.3307649457750305, -2.4980863530491013]),
    "swing_sym_ident_K": np.array(
        [
            [0.0, 0.9019333478526244, 0.4970868336621068],
            [0.9019333478526244, 0.0, 0.7047115365209683],
            [0.4970868336621068, 0.7047115365209683, 0.0],
        ]
    ),
    "swing_asym_K": np.array(
        [
            [0.0, 0.9088313401425899, 0.4915507670318054],
            [0.9032446668576976, 0.0, 0.7075263898511375],
            [0.5007483227764051, 0.696230139499009, 0.0],
        ]
    ),
    "swing_asym_P": np.array([0.5979647954022034, -0.09884580632518923, -0.4992495261344361]),
    "swing_asym_omega": np.array([2.3918591816088135, -0.32948602108396413, -2.49624763067218]),
    "integral_K": np.array(
        [
            [0.0, 0.9025741068271693, 0.4961684674583769],
            [0.9025741068271693, 0.0, 0.7059390758793358],
            [0.4961684674583769, 0.7059390758793358, 0.0],
        ]
    ),
    "integral_P": np.array([0.5985145968331952, -0.0990840191498828, -0.49943052171120716]),
    "integral_omega": np.array([2.3940583873327808, -0.33028006383294267, -2.4971526085560356]),
}

# Scalar diagnostics. The proportions are exact rationals (sparsity is a
# count ratio, score is a bounded diagnostic) and the verdicts are
# categorical, so these are checked at the same separated tolerance for
# floats and by exact equality for strings.
_GOLDEN_SCALARS: dict[str, float] = {
    "first_order_mcp_sparsity": 0.9333333333333333,
    "swing_sym_msr": 0.04004743831202507,
    "swing_sym_ident_score": 0.9996845317668399,
    "swing_asym_msr": 0.03644135053721742,
    "integral_msr": 0.037442981977247894,
    "integral_ident_score": 0.9981478637919239,
}
_GOLDEN_VERDICTS: dict[str, str] = {
    "swing_sym_ident_verdict": "ACCEPT",
    "integral_ident_verdict": "ACCEPT",
}


def _compute_golden_outputs() -> tuple[dict[str, np.ndarray], dict[str, float], dict[str, str]]:
    """Run every estimation path under pinned-deterministic BLAS.

    ``threadpool_limits(1)`` removes the intra-run thread-reduction
    component of OpenBLAS non-determinism (the SVD / lstsq / iterative
    prox reductions then sum in a single deterministic order). The
    residual cross-architecture last-bit noise is absorbed by the
    ``_RTOL``/``_ATOL`` band at the comparison site, not here.
    """
    arrays: dict[str, np.ndarray] = {}
    scalars: dict[str, float] = {}
    verdicts: dict[str, str] = {}

    with threadpool_limits(limits=1, user_api="blas"):
        pm, theta = _first_order_pm()
        dt = 0.05
        cfg = CouplingEstimationConfig(
            penalty="mcp", lambda_reg=0.15, dt=dt, max_iter=800, tol=1e-7
        )
        r1 = estimate_coupling(pm, cfg)
        arrays["first_order_mcp_K"] = np.asarray(r1.K, dtype=np.float64)
        scalars["first_order_mcp_sparsity"] = float(r1.sparsity)

        cfg_s = CouplingEstimationConfig(
            penalty="mcp",
            lambda_reg=0.02,
            dt=dt,
            max_iter=300,
            tol=1e-5,
            stability_selection=True,
            lambda_grid=(0.01, 0.03, 0.1),
            n_subsamples=4,
            subsample_fraction=0.5,
            stability_threshold=0.5,
            random_state=0,
        )
        rs = CouplingEstimator(cfg_s).estimate(pm)
        assert rs.stability_scores is not None
        arrays["first_order_stab_K"] = np.asarray(rs.K, dtype=np.float64)
        arrays["first_order_stab_scores"] = np.asarray(rs.stability_scores, dtype=np.float64)
        k_med, stab = complementary_pairs_stability(theta, cfg_s)
        arrays["cps_K_median"] = np.asarray(k_med, dtype=np.float64)
        arrays["cps_stability"] = np.asarray(stab, dtype=np.float64)

        z = np.array([-2.0, -0.3, 0.0, 0.3, 1.5, 4.0])
        arrays["mcp_prox"] = np.asarray(mcp_prox(z, 1.0, 3.0, 0.5), dtype=np.float64)
        arrays["scad_prox"] = np.asarray(scad_prox(z, 1.0, 3.7, 0.5), dtype=np.float64)
        arrays["soft_threshold"] = np.asarray(soft_threshold(z, 0.2), dtype=np.float64)

        pm2, m, d = _swing_pm()
        dt2 = 0.005
        sd = estimate_swing_coupling(pm2, m, d, dt=dt2, savgol_window=7, savgol_polyorder=4)
        arrays["swing_sym_K"] = np.asarray(sd.K, dtype=np.float64)
        arrays["swing_sym_P"] = np.asarray(sd.injection, dtype=np.float64)
        arrays["swing_sym_omega"] = np.asarray(sd.omega, dtype=np.float64)
        scalars["swing_sym_msr"] = float(sd.min_singular_ratio)
        sd_i = estimate_swing_coupling(
            pm2, m, d, dt=dt2, savgol_window=7, savgol_polyorder=4, identifiability_gate=True
        )
        assert sd_i.identifiability is not None
        arrays["swing_sym_ident_K"] = np.asarray(sd_i.K, dtype=np.float64)
        scalars["swing_sym_ident_score"] = float(sd_i.identifiability.score)
        verdicts["swing_sym_ident_verdict"] = sd_i.identifiability.verdict
        sa = estimate_swing_coupling(
            pm2, m, d, dt=dt2, symmetric=False, savgol_window=7, savgol_polyorder=4, pe_guard=False
        )
        arrays["swing_asym_K"] = np.asarray(sa.K, dtype=np.float64)
        arrays["swing_asym_P"] = np.asarray(sa.injection, dtype=np.float64)
        arrays["swing_asym_omega"] = np.asarray(sa.omega, dtype=np.float64)
        scalars["swing_asym_msr"] = float(sa.min_singular_ratio)
        ig = estimate_swing_coupling_integral(
            pm2, m, d, dt=dt2, test_support=120, n_windows=120, bump_order=6
        )
        arrays["integral_K"] = np.asarray(ig.K, dtype=np.float64)
        arrays["integral_P"] = np.asarray(ig.injection, dtype=np.float64)
        arrays["integral_omega"] = np.asarray(ig.omega, dtype=np.float64)
        scalars["integral_msr"] = float(ig.min_singular_ratio)
        ig_i = estimate_swing_coupling_integral(
            pm2,
            m,
            d,
            dt=dt2,
            test_support=120,
            n_windows=120,
            bump_order=6,
            identifiability_gate=True,
        )
        assert ig_i.identifiability is not None
        scalars["integral_ident_score"] = float(ig_i.identifiability.score)
        verdicts["integral_ident_verdict"] = ig_i.identifiability.verdict

    return arrays, scalars, verdicts


def test_golden_vectors_algorithm_preserving() -> None:
    """Every estimation path reproduces the parent-sha output.

    Algorithm-preserving proof for the strategy-registry extraction: the
    dispatcher + strategies reproduce the ``K̂`` / ``ω̂`` / ``P̂`` /
    identifiability score / PE diagnostic / prox-operator values captured
    on 65666072 before any structural change. Comparison uses the
    separated band ``_RTOL``/``_ATOL`` (see module docstring): far below
    any genuine algorithm change, far above environment-only BLAS
    last-bit noise — so it stays a real algorithm-change detector without
    flaking on cross-runner float jitter.
    """
    arrays, scalars, verdicts = _compute_golden_outputs()

    assert set(arrays) == set(_GOLDEN_ARRAYS), (
        "golden array key set drifted — a path was added/removed without "
        "updating the algorithm-preserving golden vectors"
    )
    assert set(scalars) == set(_GOLDEN_SCALARS)
    assert set(verdicts) == set(_GOLDEN_VERDICTS)

    for key, got in arrays.items():
        expected = _GOLDEN_ARRAYS[key]
        assert got.shape == expected.shape, (
            f"{key}: shape {got.shape} != golden {expected.shape} — a "
            "behaviour breach (the refactor must not change array shape)"
        )
        np.testing.assert_allclose(
            got,
            expected,
            rtol=_RTOL,
            atol=_ATOL,
            err_msg=(
                f"ALGORITHM DRIFT on path {key!r}: output left the "
                f"separated band (rtol={_RTOL}, atol={_ATOL}). This band "
                "is ~10^6x above cross-arch BLAS last-bit noise, so a "
                "breach here is a real numeric change from the parent-sha "
                "algorithm, not environment float jitter. The "
                "strategy-registry refactor is algorithm-preserving by "
                "contract."
            ),
        )

    for key, got_scalar in scalars.items():
        np.testing.assert_allclose(
            got_scalar,
            _GOLDEN_SCALARS[key],
            rtol=_RTOL,
            atol=_ATOL,
            err_msg=f"ALGORITHM DRIFT on scalar diagnostic {key!r}",
        )

    for key, got_verdict in verdicts.items():
        assert got_verdict == _GOLDEN_VERDICTS[key], (
            f"identifiability verdict {key!r} flipped: {got_verdict!r} != "
            f"{_GOLDEN_VERDICTS[key]!r} — a categorical behaviour breach"
        )


def test_golden_gate_catches_real_drift() -> None:
    """The separated-tolerance gate still fails closed on a real change.

    Verdict-flipping safeguard: it proves the move from byte-hash to
    ``assert_allclose`` did NOT defang the gate. We take a true golden
    value, perturb it by ``1e-3`` (the low end of a genuine refactor
    breach — a dropped term / wrong stencil moves a result by ≥1e-2, this
    is conservatively smaller) and assert the comparison REJECTS it. A
    perturbation ~10^6x smaller than this (pure BLAS last-bit noise) must
    instead pass, which the main test exercises every run.
    """
    truth = _GOLDEN_ARRAYS["swing_sym_K"]
    perturbed = truth.copy()
    # Perturb a single nonzero coupling edge by a real-drift-scale amount.
    perturbed[0, 1] += 1e-3
    raised = False
    try:
        np.testing.assert_allclose(perturbed, truth, rtol=_RTOL, atol=_ATOL)
    except AssertionError:
        raised = True
    assert raised, (
        "tolerance too loose — a 1e-3 (real-algorithm-change scale) "
        "perturbation slipped through the golden gate; the band must "
        "reject any drift this large or it is no longer a behaviour cap"
    )

    # And a BLAS-last-bit-scale perturbation (~1 ULP relative) must pass,
    # confirming the band is not so tight it re-introduces the flake.
    noise = truth * (1.0 + np.finfo(np.float64).eps)
    np.testing.assert_allclose(noise, truth, rtol=_RTOL, atol=_ATOL)
