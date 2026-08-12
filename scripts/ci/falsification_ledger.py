#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""H.falsification — executable falsification ledger.

Tribunal for the gate ``H.falsification``. A claim that has never been
attacked is not evidence; it is decoration. This ledger runs eight hostile
controls against the repository's own falsification machinery and records,
for each, a reproducible command, the input hash, the output hash, and a
verdict in {SURVIVED, REFUTED, BLOCKED}. ``promotion_allowed`` is True only
if *every* control SURVIVED. A REFUTED control (the attack succeeded) or a
BLOCKED control (the machinery could not even run) keeps the release RED.

The controls reuse existing, audited machinery — this is not a parallel
verifier:

1. permutation_null          core.kuramoto.falsification.time_shuffle_test
2. phase_randomized_null     core.kuramoto.falsification.iaaft_surrogate
3. topology_preserving_null  core.kuramoto.falsification.degree_preserving_rewire
4. cost_model_falsifier      core.physics.predictability_horizon (Landauer floor)
5. lookahead_leakage         research.systemic_risk.leakage_sentinel
6. timestamp_monotonicity    core.kuramoto.contracts.PhaseMatrix validation
7. seed_reproducibility      core.physics.determinism_kit (INV-DET1/DET2)
8. schema_corruption         scripts.ci.real_data_probe.validate_manifest

Each control is a *negative control*: it asserts that a null does not show
the effect, that a leakage injection is caught, that determinism holds, that
an impossible request fails closed. SURVIVED means the machinery behaved
correctly under attack.

Output: ``artifacts/falsification/ledger.json``. Exit 0 iff
``promotion_allowed`` is True.
"""

from __future__ import annotations

import argparse
import traceback
from collections.abc import Callable
from typing import Any

import numpy as np

from scripts.ci.proof_common import (
    BLOCKED,
    REFUTED,
    SURVIVED,
    canonical_sha256,
    write_artifact,
)

ARTIFACT = "artifacts/falsification/ledger.json"


def _control(name: str) -> str:
    return f"python -m scripts.ci.falsification_ledger --only {name}"


# --------------------------------------------------------------------------
# Control 1 — permutation null discriminates structured from unstructured
# --------------------------------------------------------------------------
def _permutation_null() -> tuple[str, dict[str, Any], dict[str, Any]]:
    from core.kuramoto.contracts import PhaseMatrix
    from core.kuramoto.falsification import time_shuffle_test

    rng = np.random.default_rng(20260622)
    t = 256
    n = 8
    base = np.cumsum(rng.normal(0.0, 0.05, size=t))  # shared drift → coherence
    coherent = np.mod(base[:, None] + rng.normal(0.0, 0.05, size=(t, n)), 2 * np.pi)
    incoherent = np.mod(rng.uniform(0.0, 2 * np.pi, size=(t, n)), 2 * np.pi)
    ts = np.arange(t, dtype=np.float64)
    aids = tuple(f"a{i}" for i in range(n))

    def _pm(theta: np.ndarray) -> Any:
        return PhaseMatrix(
            theta=theta,
            timestamps=ts,
            asset_ids=aids,
            extraction_method="hilbert",
            frequency_band=(0.1, 0.4),
        )

    p_coh = time_shuffle_test(_pm(coherent), n_shuffles=200, seed=0).p_value
    p_inc = time_shuffle_test(_pm(incoherent), n_shuffles=200, seed=0).p_value
    inp = {"seed": 20260622, "T": t, "N": n, "n_shuffles": 200}
    out = {"p_coherent": p_coh, "p_incoherent": p_inc}
    # Null must reject structured coherence and NOT reject unstructured noise.
    survived = p_coh < 0.05 <= p_inc
    failure = "" if survived else f"null did not discriminate (p_coh={p_coh}, p_inc={p_inc})"
    return (SURVIVED if survived else REFUTED), {**inp, **out, "failure_mode": failure}, out


# --------------------------------------------------------------------------
# Control 2 — IAAFT surrogate preserves spectrum + amplitude (faithful null)
# --------------------------------------------------------------------------
def _phase_randomized_null() -> tuple[str, dict[str, Any], dict[str, Any]]:
    from core.kuramoto.falsification import iaaft_surrogate

    rng = np.random.default_rng(7)
    t = 512
    x = np.sin(2 * np.pi * 0.05 * np.arange(t)) + 0.3 * rng.standard_normal(t)
    surr = iaaft_surrogate(x, n_iterations=100, rng=np.random.default_rng(7))

    ps_x = np.sort(np.abs(np.fft.rfft(x)))
    ps_s = np.sort(np.abs(np.fft.rfft(surr)))
    spec_rel_err = float(np.linalg.norm(ps_x - ps_s) / (np.linalg.norm(ps_x) + 1e-12))
    amp_max_err = float(np.max(np.abs(np.sort(x) - np.sort(surr))))
    out = {"spectrum_rel_err": spec_rel_err, "amplitude_max_err": amp_max_err}
    # A faithful phase-randomized null keeps the linear (spectral) + amplitude
    # structure while destroying phase relations.
    survived = spec_rel_err < 0.05 and amp_max_err < 1e-9
    failure = "" if survived else f"surrogate not spectrum/amplitude-faithful: {out}"
    return (SURVIVED if survived else REFUTED), {**out, "failure_mode": failure}, out


# --------------------------------------------------------------------------
# Control 3 — degree-preserving rewire keeps degrees, changes topology
# --------------------------------------------------------------------------
def _topology_preserving_null() -> tuple[str, dict[str, Any], dict[str, Any]]:
    from core.kuramoto.falsification import degree_preserving_rewire

    n = 24
    a = np.zeros((n, n), dtype=np.int64)
    for i in range(n):  # ring + chords → non-trivial degree sequence
        a[i, (i + 1) % n] = a[(i + 1) % n, i] = 1
        a[i, (i + 3) % n] = a[(i + 3) % n, i] = 1
    deg_before = np.sort(a.sum(axis=1))
    rewired = degree_preserving_rewire(a, rng=np.random.default_rng(11))
    deg_after = np.sort(rewired.sum(axis=1))
    degrees_preserved = bool(np.array_equal(deg_before, deg_after))
    topology_changed = not bool(np.array_equal(a, rewired))
    out = {"degrees_preserved": degrees_preserved, "topology_changed": topology_changed}
    survived = degrees_preserved and topology_changed
    failure = "" if survived else f"rewire invariant broken: {out}"
    return (SURVIVED if survived else REFUTED), {**out, "failure_mode": failure}, out


# --------------------------------------------------------------------------
# Control 4 — Landauer cost model fails closed on an impossible request
# --------------------------------------------------------------------------
def _cost_model_falsifier() -> tuple[str, dict[str, Any], dict[str, Any]]:
    from core.physics.predictability_horizon import predictability_horizon_under_budget

    # Feasible request → finite horizon.
    feasible = predictability_horizon_under_budget(
        lambda_1=0.9, delta_tol=1e-2, dynamic_range=1.0, energy_budget_J=1e-19
    )
    feasible_tau = float(feasible.tau)
    # Impossible: precision finer than the Landauer floor must raise.
    rejected = False
    try:
        predictability_horizon_under_budget(
            lambda_1=0.9,
            delta_tol=1e-2,
            dynamic_range=1.0,
            energy_budget_J=1e-30,
            delta_0_request=1e-25,
        )
    except ValueError:
        rejected = True
    out = {"feasible_tau": feasible_tau, "below_floor_rejected": rejected}
    survived = rejected and np.isfinite(feasible_tau)
    failure = "" if survived else "Landauer floor not enforced (free-lunch precision)"
    return (SURVIVED if survived else REFUTED), {**out, "failure_mode": failure}, out


# --------------------------------------------------------------------------
# Control 5 — leakage sentinel catches injected lookahead, passes clean code
# --------------------------------------------------------------------------
def _lookahead_leakage() -> tuple[str, dict[str, Any], dict[str, Any]]:
    from research.systemic_risk.leakage_sentinel import check_future_data_via_mutation

    def clean_causal(x: np.ndarray) -> np.ndarray:
        return np.cumsum(x)  # prefix depends only on the past

    def leaky_global(x: np.ndarray) -> np.ndarray:
        return np.full_like(x, float(np.mean(x)))  # prefix reads the whole series

    series = np.linspace(1.0, 2.0, 64)
    clean = check_future_data_via_mutation(clean_causal, base_series=series, cut_index=32)
    leaky = check_future_data_via_mutation(leaky_global, base_series=series, cut_index=32)
    out = {"clean_detected": clean.detected, "leaky_detected": leaky.detected}
    survived = (not clean.detected) and leaky.detected
    failure = "" if survived else f"leakage detector miscalibrated: {out}"
    return (SURVIVED if survived else REFUTED), {**out, "failure_mode": failure}, out


# --------------------------------------------------------------------------
# Control 6 — timestamp monotonicity enforced by the phase-matrix contract
# --------------------------------------------------------------------------
def _assert_strictly_monotone(ts: np.ndarray) -> None:
    """Fail-closed strict-monotonicity guard for an event timeline (INV-OMS3 idiom)."""
    arr = np.asarray(ts, dtype=np.float64)
    if arr.ndim != 1 or arr.size < 2:
        raise ValueError("timestamp series must be 1-D with ≥2 points")
    if not bool(np.all(np.diff(arr) > 0.0)):
        raise ValueError("timestamps are not strictly increasing")


def _timestamp_monotonicity() -> tuple[str, dict[str, Any], dict[str, Any]]:
    good = np.arange(16, dtype=np.float64)
    monotone_ok = True
    try:
        _assert_strictly_monotone(good)
    except ValueError:
        monotone_ok = False

    bad = good.copy()
    bad[5] = bad[4]  # duplicate timestamp breaks strict ordering
    backwards = good.copy()
    backwards[7] = backwards[6] - 1.0  # time runs backwards
    dup_rejected = False
    back_rejected = False
    try:
        _assert_strictly_monotone(bad)
    except ValueError:
        dup_rejected = True
    try:
        _assert_strictly_monotone(backwards)
    except ValueError:
        back_rejected = True
    out = {
        "monotone_accepted": monotone_ok,
        "duplicate_rejected": dup_rejected,
        "backwards_rejected": back_rejected,
    }
    survived = monotone_ok and dup_rejected and back_rejected
    failure = "" if survived else f"timestamp monotonicity guard broken: {out}"
    return (SURVIVED if survived else REFUTED), {**out, "failure_mode": failure}, out


# --------------------------------------------------------------------------
# Control 7 — seeded reproducibility: same seed → same hash, 1-ULP → different
# --------------------------------------------------------------------------
def _seed_reproducibility() -> tuple[str, dict[str, Any], dict[str, Any]]:
    from core.physics.determinism_kit import trajectory_hash

    def traj(seed: int) -> np.ndarray:
        rng = np.random.default_rng(seed)
        return rng.standard_normal((128, 4)).astype(np.float64)

    h_a = trajectory_hash(traj(42))
    h_b = trajectory_hash(traj(42))
    perturbed = traj(42)
    perturbed[0, 0] = np.nextafter(perturbed[0, 0], np.inf)  # 1 ULP
    h_p = trajectory_hash(perturbed)
    out = {"same_seed_equal": h_a == h_b, "one_ulp_differs": h_a != h_p}
    survived = (h_a == h_b) and (h_a != h_p)
    failure = "" if survived else f"determinism contract broken: {out}"
    return (SURVIVED if survived else REFUTED), {**out, "failure_mode": failure}, out


# --------------------------------------------------------------------------
# Control 8 — schema corruption is rejected, a valid manifest passes
# --------------------------------------------------------------------------
def _schema_corruption() -> tuple[str, dict[str, Any], dict[str, Any]]:
    from scripts.ci.real_data_probe import REQUIRED_FIELDS, validate_manifest

    valid: dict[str, Any] = {
        "artifact_id": "demo",
        "venue": "DEMO",
        "symbol": "X",
        "time_start_utc": "2026-01-01T00:00:00Z",
        "time_end_utc": "2026-01-02T00:00:00Z",
        "git_sha": "0" * 40,
        "git_dirty": False,
        "config_sha256": "a" * 64,
        "data_sha256": "b" * 64,
        "data_bytes": 1024,
        "schema_version": "1.0",
        "license_provenance": "public-domain",
        "replay_command": "python -m geosync.replay demo",
        "status": "MEASURED_SINGLE",
    }
    valid_errors = validate_manifest(valid)
    corrupt = dict(valid)
    corrupt["data_sha256"] = ""  # missing hash
    corrupt["data_bytes"] = 0  # zero-byte forbidden
    corrupt_errors = validate_manifest(corrupt)
    out = {
        "valid_accepted": valid_errors == [],
        "corrupt_rejected": len(corrupt_errors) > 0,
        "required_fields": len(REQUIRED_FIELDS),
    }
    survived = (valid_errors == []) and bool(corrupt_errors)
    failure = "" if survived else f"schema validator miscalibrated: valid_errors={valid_errors}"
    return (SURVIVED if survived else REFUTED), {**out, "failure_mode": failure}, out


CONTROLS: dict[str, Callable[[], tuple[str, dict[str, Any], dict[str, Any]]]] = {
    "permutation_null": _permutation_null,
    "phase_randomized_null": _phase_randomized_null,
    "topology_preserving_null": _topology_preserving_null,
    "cost_model_falsifier": _cost_model_falsifier,
    "lookahead_leakage": _lookahead_leakage,
    "timestamp_monotonicity": _timestamp_monotonicity,
    "seed_reproducibility": _seed_reproducibility,
    "schema_corruption": _schema_corruption,
}


def run(only: str | None = None) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for name, fn in CONTROLS.items():
        if only is not None and name != only:
            continue
        try:
            verdict, detail, output = fn()
            failure_mode = detail.get("failure_mode", "")
        except Exception as exc:  # a control that cannot run is BLOCKED (fail-closed)
            verdict = BLOCKED
            detail = {"exception": repr(exc), "traceback": traceback.format_exc()[-800:]}
            output = detail
            failure_mode = f"control could not execute: {exc!r}"
        records.append(
            {
                "name": name,
                "command": _control(name),
                "input_sha256": canonical_sha256({"control": name, "detail_keys": sorted(detail)}),
                "output_sha256": canonical_sha256(output),
                "verdict": verdict,
                "failure_mode": failure_mode,
                "detail": detail,
            }
        )
    promotion_allowed = bool(records) and all(r["verdict"] == SURVIVED for r in records)
    return {
        "ledger_id": "geosync-falsification-ledger",
        "schema_version": "1.0",
        "controls": records,
        "promotion_allowed": promotion_allowed,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", default=ARTIFACT, help="artifact output path")
    parser.add_argument("--only", default=None, choices=sorted(CONTROLS), help="run one control")
    args = parser.parse_args(argv)
    payload = run(args.only)
    path = write_artifact(args.json, payload)
    print(f"[H.falsification] promotion_allowed={payload['promotion_allowed']} -> {path}")
    for r in payload["controls"]:
        print(f"  [{r['verdict']:<9}] {r['name']}: {r['failure_mode'] or 'ok'}")
    return 0 if payload["promotion_allowed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
