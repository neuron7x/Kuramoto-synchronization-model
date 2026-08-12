# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""CALIB-GRID-002 — integral / weak-form swing identifier calibration.

A NEW pre-registered lineage attacking the proven CALIB-GRID-001 / R1
*differential-class* boundary with a different estimator class: the weak
/ integral form (Messenger & Bortz, *Weak SINDy*, J. Comput. Phys. 443
(2021) 110525). The phase is never double-differentiated.

The gates below mirror ``PREREGISTRATION_002.yaml`` byte-for-numeric; a
no-peek drift test fails closed if the doc and this module diverge. The
frozen CALIB-GRID-001 / R1 pre-registration, gates, seeds, σ, θ₀ and
decision rule are **untouched** — CALIB-GRID-002 carries its own
``cg002.*`` gates and its own ledger.
"""

from __future__ import annotations

import json
import platform
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from core.kuramoto.coupling_estimator import (
    PersistentExcitationError,
    estimate_swing_coupling_integral,
)
from core.kuramoto.identifiability import PE_HARD_FLOOR, IdentifiabilityVerdict

from .._substrate import (
    FROZEN_PREREG_SHA,
    PARENT_LEDGER_SHA256,
    PREREG_BRANCH_BASE_SHA,
    ledger_sha256,
)
from .._substrate import Gate as CG002Gate
from .._substrate import topology_f1 as _topology_f1
from ..calibration import SimConfig, ground_truth, simulate_phases
from ..grid_data import GridSystem, wscc_9_bus

__all__ = [
    "CG002_BUMP_ORDER",
    "CG002_TEST_SUPPORT",
    "CG002_N_WINDOWS",
    "CG002_NOISELESS_GATES",
    "CG002_NOISY_GATES",
    "CG002_THEOREM_GATE",
    "CG002_NULL_FPR_GATE",
    "CG002Gate",
    "CG002Metrics",
    "dcb_phase_cohesiveness_rel_error",
    "recover_coupling_integral",
    "run_cg002_calibration",
    "null_battery_fpr",
    "build_cg002_ledger",
]

# --- Frozen weak-form solver constants (mirror PREREGISTRATION_002.yaml) --
# Chosen from the SIGNAL CLASS, not the gate (see PROVENANCE_002.md § 2):
# (1-s²)^6 is the canonical C⁵ Messenger–Bortz compact test function; a
# 1.2 s integration window low-passes σ=0.02 while staying inside the
# ~0.5 s over-damped relative-angle excursion of the 48 s kept transient;
# 400 windows over-determine the global solve. The PE guard uses the
# THEORY half-mantissa floor already in the merged codebase
# (``core.kuramoto.identifiability.PE_HARD_FLOOR``) — not a retune.
CG002_BUMP_ORDER: int = 6
CG002_TEST_SUPPORT: int = 120
CG002_N_WINDOWS: int = 400

# --- Pre-registered, frozen. Mirror of PREREGISTRATION_002.yaml. ---------

CG002_NOISELESS_GATES: tuple[CG002Gate, ...] = (
    CG002Gate(
        name="cg002.noiseless.frobenius",
        metric_key="frobenius_rel_error",
        operator="<=",
        threshold=0.10,
        localises_to="weak-form design conditioning on the over-damped transient",
    ),
    CG002Gate(
        name="cg002.noiseless.topology_f1",
        metric_key="topology_f1",
        operator=">=",
        threshold=0.95,
        localises_to="weak-form edge-support thresholding",
    ),
)

CG002_NOISY_GATES: tuple[CG002Gate, ...] = (
    CG002Gate(
        name="cg002.noisy.frobenius",
        metric_key="frobenius_rel_error",
        operator="<=",
        threshold=0.25,
        localises_to="regressor-level coupling SNR at the frozen sigma=0.02",
    ),
    CG002Gate(
        name="cg002.noisy.topology_f1",
        metric_key="topology_f1",
        operator=">=",
        threshold=0.90,
        localises_to="weak-form support stability under sigma",
    ),
)

CG002_THEOREM_GATE: CG002Gate = CG002Gate(
    name="cg002.noiseless.dcb_consistency",
    metric_key="dcb_phase_cohesiveness_rel_error",
    operator="<=",
    threshold=0.15,
    localises_to="Dorfler-Chertkov-Bullo DC-power-flow consistency of (K_hat, P_hat)",
)

CG002_NULL_FPR_GATE: CG002Gate = CG002Gate(
    name="cg002.null_fpr",
    metric_key="empirical_fpr",
    operator="<=",
    threshold=0.05,
    localises_to="specificity of the weak-form edge support under nulls",
)


@dataclass(frozen=True)
class CG002Metrics:
    """Machine-readable result ledger for one CALIB-GRID-002 regime."""

    regime: str
    frobenius_rel_error: float
    topology_f1: float
    dcb_phase_cohesiveness_rel_error: float
    front_gate_verdict: str
    front_gate_score: float
    front_gate_r_squared: float
    reciprocal_condition: float
    n_nodes: int
    n_true_edges: int
    n_recovered_edges: int
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable view (sorted keys downstream)."""
        return {
            "regime": self.regime,
            "frobenius_rel_error": self.frobenius_rel_error,
            "topology_f1": self.topology_f1,
            "dcb_phase_cohesiveness_rel_error": self.dcb_phase_cohesiveness_rel_error,
            "front_gate_verdict": self.front_gate_verdict,
            "front_gate_score": self.front_gate_score,
            "front_gate_r_squared": self.front_gate_r_squared,
            "reciprocal_condition": self.reciprocal_condition,
            "n_nodes": self.n_nodes,
            "n_true_edges": self.n_true_edges,
            "n_recovered_edges": self.n_recovered_edges,
            "extra": self.extra,
        }


def _weighted_laplacian(k: NDArray[np.float64]) -> NDArray[np.float64]:
    """``L = diag(K·1) − K`` for a symmetric non-negative coupling."""
    return np.asarray(np.diag(k.sum(axis=1)) - k, dtype=np.float64)


def _oriented_incidence(
    k: NDArray[np.float64],
) -> tuple[NDArray[np.float64], list[tuple[int, int]]]:
    """Oriented incidence ``B`` over the active edges ``i<j, |K_ij|>0``."""
    n = k.shape[0]
    edges = [(i, j) for i in range(n) for j in range(i + 1, n) if abs(k[i, j]) > 0.0]
    m = len(edges)
    inc = np.zeros((n, m), dtype=np.float64)
    for e, (i, j) in enumerate(edges):
        inc[i, e] = 1.0
        inc[j, e] = -1.0
    return inc, edges


def dcb_phase_cohesiveness_rel_error(
    k_true: NDArray[np.float64],
    p_true: NDArray[np.float64],
    k_hat: NDArray[np.float64],
    p_hat: NDArray[np.float64],
) -> float:
    r"""Dörfler–Chertkov–Bullo DC-power-flow consistency (theorem-class).

    A **non-circular** metric, independent of ``‖K̂−K‖`` and of the
    critical-coupling scale. The DCB small-signal (DC-power-flow) steady
    state is ``δ* = L(K)⁺ P`` and the predicted per-edge
    phase-cohesiveness vector is ``Bᵀ δ*`` (Dörfler, Chertkov & Bullo,
    *Synchronization in complex oscillator networks and smart grids*,
    PNAS 110(6) (2013) 2005, Eq. (2)–(3)). We compare the prediction
    built from the recovered ``(K̂, P̂)`` against the one from the true
    ``(K, P)``:

    .. math::

        \frac{\bigl\| B(\hat K)^\top L(\hat K)^{+}\hat P
              - B(K)^\top L(K)^{+}P \bigr\|_2}
             {\bigl\| B(K)^\top L(K)^{+}P \bigr\|_2} .

    The incidence ``B`` is taken on the **true** active-edge set for
    both terms so the comparison is on the same edge basis (a recovered
    edge that is structurally wrong is penalised through ``L(K̂)⁺``, not
    silently dropped).

    Returns
    -------
    float
        Relative error; ``+inf`` if the true cohesiveness vector is the
        zero vector (no signal to be consistent with — fail-closed).
    """
    inc_true, _ = _oriented_incidence(k_true)
    lap_true = _weighted_laplacian(k_true)
    lap_hat = _weighted_laplacian(np.abs(k_hat))
    delta_true = np.linalg.pinv(lap_true) @ p_true
    delta_hat = np.linalg.pinv(lap_hat) @ p_hat
    coh_true = inc_true.T @ delta_true
    coh_hat = inc_true.T @ delta_hat
    denom = float(np.linalg.norm(coh_true))
    if denom <= 0.0:
        return float("inf")
    return float(np.linalg.norm(coh_hat - coh_true) / denom)


@dataclass(frozen=True)
class _Recovery:
    """One weak-form recovery (true vs recovered system + front-gate)."""

    k_true: NDArray[np.float64]
    k_hat: NDArray[np.float64]
    p_true: NDArray[np.float64]
    p_hat: NDArray[np.float64]
    front_verdict: str
    front_score: float
    front_r_squared: float
    reciprocal_condition: float


def recover_coupling_integral(
    system: GridSystem,
    cfg: SimConfig,
    *,
    noisy: bool,
) -> _Recovery:
    """Simulate the frozen trajectory → recover via the weak/integral path.

    The simulation is the *same* frozen ``SimConfig`` as CALIB-GRID-001
    (only the estimator class differs). The PE guard uses the theory
    ``PE_HARD_FLOOR`` (not a retune). The identifiability front-gate is
    evaluated under the integral estimator so the before→after (REFUSE
    under differential → verdict under integral) can be reported. The
    recovered injection ``P̂ = ω̂·d`` is threaded out so the
    Dörfler–Chertkov–Bullo metric is a function of the *recovered*
    system (non-circular).
    """
    run_cfg = cfg if noisy else replace(cfg, noise_sigma=0.0)
    k_true, omega_true = ground_truth(system, run_cfg.coupling_scale)
    phases, _ = simulate_phases(system, k_true, omega_true, run_cfg)
    d = np.asarray(system.damping, dtype=np.float64)
    # ``ground_truth`` mean-centres ``ω`` and uses ``ω = P/d``; the true
    # injection in the same (mean-centred) gauge is therefore ``ω·d``.
    p_true = np.asarray(omega_true, dtype=np.float64) * d

    est = estimate_swing_coupling_integral(
        phases,
        np.asarray(system.inertia, dtype=np.float64),
        d,
        dt=run_cfg.dt,
        test_support=CG002_TEST_SUPPORT,
        n_windows=CG002_N_WINDOWS,
        bump_order=CG002_BUMP_ORDER,
        pe_min_singular_ratio=PE_HARD_FLOOR,
        pe_guard=True,
        identifiability_gate=True,
    )
    rep = est.identifiability
    assert rep is not None  # symmetric joint solve + gate ⇒ always present
    # Recovered injection in the same mean-centred gauge as ``p_true``.
    p_hat = np.asarray(est.omega, dtype=np.float64) * d
    p_hat = p_hat - float(np.mean(p_hat))
    return _Recovery(
        k_true=np.asarray(k_true, dtype=np.float64),
        k_hat=np.asarray(est.K, dtype=np.float64),
        p_true=np.asarray(p_true - float(np.mean(p_true)), dtype=np.float64),
        p_hat=p_hat,
        front_verdict=rep.verdict.value,
        front_score=float(rep.score),
        front_r_squared=float(rep.r_squared),
        reciprocal_condition=float(est.min_singular_ratio),
    )


def run_cg002_calibration(
    system: GridSystem,
    cfg: SimConfig,
    *,
    noisy: bool,
) -> CG002Metrics:
    """End-to-end one-regime CALIB-GRID-002 calibration (weak/integral)."""
    rec = recover_coupling_integral(system, cfg, noisy=noisy)
    k_true, k_hat = rec.k_true, rec.k_hat
    fro_true = float(np.linalg.norm(k_true, ord="fro"))
    fro_err = float(np.linalg.norm(k_hat - k_true, ord="fro"))
    frob_rel = fro_err / fro_true if fro_true > 0.0 else float("inf")
    f1, n_true, n_hat = _topology_f1(k_true, k_hat, cfg.topology_rel_threshold)
    dcb = dcb_phase_cohesiveness_rel_error(k_true, rec.p_true, k_hat, rec.p_hat)
    fv, fs, fr2, rcond = (
        rec.front_verdict,
        rec.front_score,
        rec.front_r_squared,
        rec.reciprocal_condition,
    )
    return CG002Metrics(
        regime="noisy" if noisy else "noiseless",
        frobenius_rel_error=frob_rel,
        topology_f1=f1,
        dcb_phase_cohesiveness_rel_error=dcb,
        front_gate_verdict=fv,
        front_gate_score=fs,
        front_gate_r_squared=fr2,
        reciprocal_condition=rcond,
        n_nodes=int(k_true.shape[0]),
        n_true_edges=n_true,
        n_recovered_edges=n_hat,
        extra={"fro_true": fro_true, "fro_abs_error": fro_err},
    )


def _offdiag(a: NDArray[np.float64]) -> NDArray[np.float64]:
    """Flatten the strictly off-diagonal entries of a square matrix."""
    n = a.shape[0]
    off = ~np.eye(n, dtype=bool)
    return np.asarray(a[off], dtype=np.float64)


def _weight_corr(k_a: NDArray[np.float64], k_b: NDArray[np.float64]) -> float:
    """Pearson correlation of the off-diagonal coupling-weight patterns.

    WSCC-9 is a *complete* graph, so binary edge-support F1 is trivially
    1.0 for any permutation and cannot test specificity. The
    discriminating statistic is whether the recovered **weight pattern**
    tracks the *true* weight pattern: a sound recovery correlates highly
    with the true ``K``; a null that destroyed the structure must not.
    """
    a = np.abs(_offdiag(k_a))
    b = np.abs(_offdiag(k_b))
    if a.std() <= 1e-12 or b.std() <= 1e-12:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def null_battery_fpr(
    system: GridSystem,
    cfg: SimConfig,
    *,
    n_trials: int = 12,
    corr_fp_threshold: float = 0.8,
) -> tuple[float, dict[str, Any]]:
    """Empirical false-positive rate of the weak-form weight recovery.

    Two nulls (mirroring the existing CALIB nulls, minimal). WSCC-9 is a
    complete graph, so binary support F1 is degenerate; the
    discriminating read-out is the **weight-pattern correlation** with
    the *true* ``K``:

    * **topology-preserving payload shuffle** — permute the per-node
      phase columns (each node's marginal dynamics and the global record
      length preserved, the true *pairing* destroyed). A *false
      positive* is a shuffled-data ``K̂`` that still correlates with the
      original true ``K`` above ``corr_fp_threshold`` — i.e. the
      instrument hallucinated the original structure from destroyed
      data.
    * **flat-coupling placebo** — simulate with a uniform coupling so
      there is no weight contrast; a *false positive* is a recovered
      ``K̂`` whose dispersion (CV of the off-diagonal magnitudes)
      exceeds ``1.0`` — i.e. the instrument manufactured contrast.

    Returns ``(empirical_fpr, detail)``.
    """
    from core.kuramoto.contracts import PhaseMatrix

    k_true, omega_true = ground_truth(system, cfg.coupling_scale)
    base_cfg = replace(cfg, noise_sigma=0.0)
    phases, _ = simulate_phases(system, k_true, omega_true, base_cfg)
    theta = np.asarray(phases.theta, dtype=np.float64)
    n = system.n
    m = np.asarray(system.inertia, dtype=np.float64)
    d = np.asarray(system.damping, dtype=np.float64)

    false_positives = 0
    trials = 0
    rng = np.random.default_rng(cfg.seed + 202)
    corrs: list[float] = []

    # Null 1 — topology-preserving payload shuffle (weight-pattern test).
    for _ in range(n_trials):
        perm = rng.permutation(n)
        if np.array_equal(perm, np.arange(n)):
            continue
        shuffled = np.mod(theta[:, perm], 2.0 * np.pi)
        shuffled = np.clip(shuffled, 0.0, np.nextafter(2.0 * np.pi, 0.0))
        pm = PhaseMatrix(
            theta=shuffled,
            timestamps=np.asarray(phases.timestamps, dtype=np.float64),
            asset_ids=system.bus_ids,
            extraction_method="hilbert",
            frequency_band=(1e-6, 0.5),
        )
        trials += 1
        try:
            est = estimate_swing_coupling_integral(
                pm,
                m,
                d,
                dt=cfg.dt,
                test_support=CG002_TEST_SUPPORT,
                n_windows=CG002_N_WINDOWS,
                bump_order=CG002_BUMP_ORDER,
                pe_min_singular_ratio=PE_HARD_FLOOR,
                pe_guard=False,
            )
        except PersistentExcitationError:
            # Fail-closed on a degenerate null draw is the *correct*
            # (negative) outcome — no hallucinated structure.
            continue
        c = _weight_corr(k_true, np.asarray(est.K, dtype=np.float64))
        corrs.append(c)
        if c > corr_fp_threshold:
            false_positives += 1

    # Null 2 — flat-coupling placebo (no weight contrast to recover).
    flat = np.full((n, n), float(np.mean(k_true[k_true > 0.0])), dtype=np.float64)
    np.fill_diagonal(flat, 0.0)
    flat_phases, _ = simulate_phases(system, flat, omega_true, base_cfg)
    trials += 1
    try:
        est_flat = estimate_swing_coupling_integral(
            flat_phases,
            m,
            d,
            dt=cfg.dt,
            test_support=CG002_TEST_SUPPORT,
            n_windows=CG002_N_WINDOWS,
            bump_order=CG002_BUMP_ORDER,
            pe_min_singular_ratio=PE_HARD_FLOOR,
            pe_guard=False,
        )
        kf = np.abs(_offdiag(np.asarray(est_flat.K, dtype=np.float64)))
        disp = float(kf.std() / (kf.mean() + 1e-12))
        flat_false_positive = bool(disp > 1.0)
    except PersistentExcitationError:
        flat_false_positive = False
        disp = 0.0
    if flat_false_positive:
        false_positives += 1

    fpr = false_positives / trials if trials > 0 else 0.0
    return fpr, {
        "n_trials": trials,
        "n_false_positives": false_positives,
        "shuffle_null": "topology-preserving payload shuffle (weight-pattern correlation)",
        "shuffle_corr_fp_threshold": corr_fp_threshold,
        "shuffle_max_corr_with_true_K": max(corrs) if corrs else None,
        "placebo_null": "flat-coupling placebo (off-diagonal dispersion read-out)",
        "placebo_dispersion": disp,
    }


def build_cg002_ledger(
    system: GridSystem,
    cfg: SimConfig,
) -> dict[str, Any]:
    """Run both regimes + theorem-class + nulls → sha-pinned ledger.

    The verdict is computed only from the pre-registered ``cg002.*``
    gates (read, not redefined). The frozen CALIB-GRID-001 / R1 gates
    are not touched.
    """
    noiseless = run_cg002_calibration(system, cfg, noisy=False)
    noisy = run_cg002_calibration(system, cfg, noisy=True)
    fpr, null_detail = null_battery_fpr(system, cfg)

    gate_rows: list[dict[str, Any]] = []

    def _emit(gate: CG002Gate, observed: float) -> bool:
        passed = gate.check(observed)
        gate_rows.append(
            {
                "name": gate.name,
                "metric_key": gate.metric_key,
                "observed": observed,
                "operator": gate.operator,
                "threshold": gate.threshold,
                "passed": passed,
                "localises_to": gate.localises_to,
            }
        )
        return passed

    nl_d = noiseless.to_dict()
    ny_d = noisy.to_dict()
    all_pass = True
    for g in CG002_NOISELESS_GATES:
        all_pass &= _emit(g, float(nl_d[g.metric_key]))
    for g in CG002_NOISY_GATES:
        all_pass &= _emit(g, float(ny_d[g.metric_key]))
    all_pass &= _emit(CG002_THEOREM_GATE, float(nl_d[CG002_THEOREM_GATE.metric_key]))
    all_pass &= _emit(CG002_NULL_FPR_GATE, fpr)

    # Binary front-gate gate: under the integral estimator the front-gate
    # is expected to ACCEPT the σ=0.02 case (the falsifiable claim's
    # #2↔#1 leg). Pre-registered as a binary gate.
    front_accepts_noisy = noisy.front_gate_verdict == IdentifiabilityVerdict.ACCEPT.value
    gate_rows.append(
        {
            "name": "cg002.front_gate_accepts_noisy_integral",
            "kind": "binary",
            "expectation": "ACCEPT",
            "observed": noisy.front_gate_verdict,
            "passed": bool(front_accepts_noisy),
            "localises_to": (
                "identifiability front-gate under the integral estimator at sigma=0.02"
            ),
        }
    )
    all_pass &= bool(front_accepts_noisy)

    verdict = "PASS" if all_pass else "NEGATIVE"
    failed = [g for g in gate_rows if not g["passed"]]

    ledger: dict[str, Any] = {
        "artifact": "CALIB-GRID-002",
        "kind": "external-ground-truth-calibration",
        "is_hypothesis": False,
        "is_science_claim": False,
        "lineage": "CALIB-GRID-002 (new pre-registered lineage, integral/weak-form)",
        "parent_lineages": [
            "PR #749 (CALIB-GRID-001)",
            "PR #751 (R1 differential swing)",
            "PR #755 (identifiability front-gate)",
        ],
        "frozen_preregistration_sha": FROZEN_PREREG_SHA,
        "parent_ledger_sha256": PARENT_LEDGER_SHA256,
        "prereg_branch_base_sha": PREREG_BRANCH_BASE_SHA,
        "estimator": (
            "core.kuramoto.coupling_estimator.estimate_swing_coupling_integral "
            f"(weak/integral form, bump_order={CG002_BUMP_ORDER}, "
            f"test_support={CG002_TEST_SUPPORT}, n_windows={CG002_N_WINDOWS}, "
            "pe_guard at PE_HARD_FLOOR=sqrt(eps))"
        ),
        "literature_anchor": (
            "Messenger & Bortz, Weak SINDy, J. Comput. Phys. 443 (2021) "
            "110525; Dorfler-Chertkov-Bullo PNAS 110(6) (2013) 2005"
        ),
        "system": system.name,
        "citation": system.citation,
        "python": platform.python_version(),
        "config": {
            "coupling_scale": cfg.coupling_scale,
            "dt": cfg.dt,
            "steps": cfg.steps,
            "keep_frac": cfg.keep_frac,
            "theta0_perturb": cfg.theta0_perturb,
            "seed": cfg.seed,
            "noise_sigma": cfg.noise_sigma,
            "topology_rel_threshold": cfg.topology_rel_threshold,
            "bump_order": CG002_BUMP_ORDER,
            "test_support": CG002_TEST_SUPPORT,
            "n_windows": CG002_N_WINDOWS,
        },
        "metrics": {"noiseless": nl_d, "noisy": ny_d},
        "null_battery": {"empirical_fpr": fpr, **null_detail},
        "gates": gate_rows,
        "verdict": verdict,
        "failed_gates": failed,
        "pandapower_parity": (
            "DEFERRED — pandapower not importable in env; not a runtime "
            "dependency; not on the WSCC-9 critical path; reproduction "
            "command in PROVENANCE_002.md § 4"
        ),
    }
    ledger["ledger_sha256"] = ledger_sha256(ledger)
    return ledger


def _default_ledger() -> dict[str, Any]:
    return build_cg002_ledger(wscc_9_bus(), SimConfig())


if __name__ == "__main__":  # pragma: no cover
    import sys

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    led = _default_ledger()
    text = json.dumps(led, indent=2, sort_keys=True)
    if out is not None:
        out.write_text(text + "\n", encoding="utf-8")
    print(text)
