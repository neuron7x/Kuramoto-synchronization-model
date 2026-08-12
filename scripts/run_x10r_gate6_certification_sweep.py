# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002B — Gate 6 high-budget power certification sweep driver.

Parallel implementation. Per-(N, λ, seed) work units are dispatched
to a process pool sized at ``cpu_count - 4`` (≤12 by default) so the
sweep saturates compute cores while leaving headroom for the OS/UI.

Sweep grid (issue #652):

    N           ∈ {50, 100, 200, 400}
    λ           ∈ {0.0, 0.05, 0.10, 0.20, 0.40, 1.0}
    n_seeds     = 20
    n_bootstrap = 16

Determinism: each (N, λ, seed_idx) maps to the same RNG seed used
by the sequential ``compute_sensitivity_surface`` driver, so the
parallel and sequential drivers produce identical SensitivityCell
contents — only the wallclock differs. Aggregation is order-
invariant (counts, medians).

Strict scope: synthetic only. NO real-data verdict. NO source-code
change. NO INV-IDENTIFICATION-1 lift.

Bibliographic anchors justify model class and reviewer traceability;
operational validity is determined only by gates, positive/negative
controls, null distributions, capsules, and power/FPR/MDE evidence.
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

from research.reconstruction.kuramoto_on_reconstruction import (
    DEFAULT_BOOTSTRAP_SEEDS,
    DEFAULT_K_TEST_RATIO,
    MIN_PRECURSOR_GAP,
    PrecursorDirection,
    gate_6_precursor_discriminative,
)
from research.reconstruction.positive_control import ground_truth_core_periphery
from research.reconstruction.sensitivity_surface import (
    SensitivityCell,
    SensitivitySurface,
    mix_substrate_with_null,
)


def _init_worker() -> None:
    """Lower priority on each worker so the OS/UI stays responsive."""
    try:
        os.nice(10)
    except OSError:
        pass


def _run_one_seed(args: tuple[int, float, int, int, float, int, float]) -> dict[str, Any]:
    """Run one (N, λ, seed_idx) cell-fragment.

    Returns a flat dict so process-pool pickle/unpickle stays cheap.
    The seed scheme matches the sequential driver verbatim.
    """
    n, lam, seed_idx, substrate_seed, k_ratio, n_bootstrap, min_gap = args
    w_substrate = ground_truth_core_periphery(n=n, core_frac=0.30, seed=substrate_seed)
    seed_val = substrate_seed * 1000 + n * 31 + int(lam * 1000) + seed_idx
    rng_mix = np.random.default_rng(seed_val)
    w_mixed = mix_substrate_with_null(w_substrate, lambda_mix=lam, rng=rng_mix)
    report = gate_6_precursor_discriminative(
        w_mixed,
        seed=seed_val + 7,
        k_ratio=k_ratio,
        n_bootstrap=n_bootstrap,
        min_gap=min_gap,
    )
    return {
        "n": int(n),
        "lam": float(lam),
        "seed_idx": int(seed_idx),
        "passed": bool(report.passed),
        "direction": report.direction.name,
        "delta_r_median": float(report.delta_r_median),
        "ci_width": float(report.delta_r_ci_high - report.delta_r_ci_low),
    }


def _aggregate_to_surface(
    results: list[dict[str, Any]],
    *,
    n_grid: tuple[int, ...],
    lambda_grid: tuple[float, ...],
    n_seeds: int,
) -> SensitivitySurface:
    cells: list[SensitivityCell] = []
    for n in n_grid:
        for lam in lambda_grid:
            seed_results = [r for r in results if r["n"] == n and abs(r["lam"] - lam) < 1e-12]
            n_pass = sum(1 for r in seed_results if r["passed"])
            n_fac = sum(
                1
                for r in seed_results
                if r["direction"] == PrecursorDirection.SYNCHRONIZATION_FACILITATED.name
            )
            n_hind = sum(
                1
                for r in seed_results
                if r["direction"] == PrecursorDirection.SYNCHRONIZATION_HINDERED.name
            )
            n_nosig = len(seed_results) - n_fac - n_hind
            delta_rs = [r["delta_r_median"] for r in seed_results]
            ci_widths = [r["ci_width"] for r in seed_results]
            cells.append(
                SensitivityCell(
                    n_nodes=int(n),
                    lambda_mix=float(lam),
                    n_seeds=int(n_seeds),
                    n_pass=int(n_pass),
                    n_facilitated=int(n_fac),
                    n_hindered=int(n_hind),
                    n_no_signal=int(n_nosig),
                    median_delta_r=float(np.median(delta_rs)) if delta_rs else 0.0,
                    median_ci_width=float(np.median(ci_widths)) if ci_widths else 0.0,
                    median_abs_delta_r=(float(np.median(np.abs(delta_rs))) if delta_rs else 0.0),
                )
            )

    zero_cells = [c for c in cells if c.lambda_mix == 0.0]
    fpr = float(np.mean([c.power for c in zero_cells])) if zero_cells else 0.0

    mde: dict[int, float] = {}
    for n in n_grid:
        cells_for_n = sorted((c for c in cells if c.n_nodes == n), key=lambda c: c.lambda_mix)
        found = False
        for c in cells_for_n:
            if c.power >= 0.80:
                mde[int(n)] = float(c.lambda_mix)
                found = True
                break
        if not found:
            mde[int(n)] = float("inf")

    return SensitivitySurface(
        n_grid=tuple(int(n) for n in n_grid),
        lambda_grid=tuple(float(x) for x in lambda_grid),
        n_seeds=int(n_seeds),
        cells=tuple(cells),
        fpr_estimate=fpr,
        mde_lambda_per_n=mde,
    )


def _classify(surface: SensitivitySurface) -> tuple[str, dict[str, float | bool]]:
    """Apply the D-002B certification rule per the protocol."""
    fpr_zero_cells = [c for c in surface.cells if c.lambda_mix == 0.0]
    fpr_max = max((c.power for c in fpr_zero_cells), default=0.0)
    power_below_one = [c.power for c in surface.cells if 0.0 < c.lambda_mix < 1.0]
    power_max_below_one = max(power_below_one, default=0.0)
    cells_at_one = [c for c in surface.cells if c.lambda_mix == 1.0]
    ci_vs_dr_pass = all(
        c.median_ci_width < c.median_abs_delta_r for c in cells_at_one if c.median_abs_delta_r > 0
    )

    fpr_ok = fpr_max <= 0.05
    power_ok = power_max_below_one >= 0.80

    if fpr_ok and power_ok and ci_vs_dr_pass:
        verdict = "SYNTHETIC_GATE6_CERTIFIED"
    else:
        verdict = "GATE6_NOT_CERTIFIED_AT_TESTED_BUDGET"

    metrics: dict[str, float | bool] = {
        "fpr_max_at_lambda_zero": fpr_max,
        "power_max_below_lambda_one": power_max_below_one,
        "fpr_rule_pass": fpr_ok,
        "power_rule_pass": power_ok,
        "ci_vs_dr_pass": ci_vs_dr_pass,
    }
    return verdict, metrics


def main() -> int:
    n_grid: tuple[int, ...] = (50, 100, 200, 400)
    lambda_grid: tuple[float, ...] = (0.0, 0.05, 0.10, 0.20, 0.40, 1.0)
    n_seeds = 20
    n_bootstrap = int(os.environ.get("D002B_NBOOT", "16"))
    if n_bootstrap < 1:
        n_bootstrap = DEFAULT_BOOTSTRAP_SEEDS
    substrate_seed = 42
    k_ratio = DEFAULT_K_TEST_RATIO
    min_gap = MIN_PRECURSOR_GAP

    cpu = os.cpu_count() or 4
    n_workers = max(1, cpu - 4)
    n_workers = int(os.environ.get("D002B_WORKERS", str(n_workers)))

    work: list[tuple[int, float, int, int, float, int, float]] = [
        (n, lam, s, substrate_seed, k_ratio, n_bootstrap, min_gap)
        for n in n_grid
        for lam in lambda_grid
        for s in range(n_seeds)
    ]

    print(
        f"D-002B sweep starting (parallel)\n"
        f"  N grid       = {n_grid}\n"
        f"  λ grid       = {lambda_grid}\n"
        f"  n_seeds      = {n_seeds}\n"
        f"  n_bootstrap  = {n_bootstrap}\n"
        f"  cells        = {len(n_grid) * len(lambda_grid)}\n"
        f"  work units   = {len(work)}\n"
        f"  workers      = {n_workers} of {cpu} cores (4 reserved for OS/UI, nice +10)\n"
        f"  scope        = synthetic only; NO real-data verdict; NO INV lift",
        flush=True,
    )

    results: list[dict[str, Any]] = []
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=n_workers, initializer=_init_worker) as ex:
        for i, r in enumerate(ex.map(_run_one_seed, work, chunksize=1), start=1):
            results.append(r)
            if i % 24 == 0 or i == len(work):
                pct = 100.0 * i / len(work)
                el = time.time() - t0
                eta = el * (len(work) - i) / max(i, 1)
                print(
                    f"  ... {i}/{len(work)} ({pct:.1f}%) elapsed={el:.0f}s eta={eta:.0f}s",
                    flush=True,
                )
    elapsed = time.time() - t0

    surface = _aggregate_to_surface(
        results, n_grid=n_grid, lambda_grid=lambda_grid, n_seeds=n_seeds
    )
    verdict, metrics = _classify(surface)

    out_path = Path("tmp/x10r_gate6_certification_sweep.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = surface.to_dict()
    payload["elapsed_seconds"] = elapsed
    payload["n_workers"] = n_workers
    payload["n_bootstrap"] = n_bootstrap
    payload["verdict"] = verdict
    payload["certification_metrics"] = metrics
    out_path.write_text(json.dumps(payload, indent=2))

    print(
        f"\nD-002B sweep done in {elapsed:.0f}s ({elapsed / 60:.1f} min).\n"
        f"  FPR (max power at λ=0)    = {metrics['fpr_max_at_lambda_zero']:.3f}  rule ≤0.05  → "
        f"{'PASS' if metrics['fpr_rule_pass'] else 'FAIL'}\n"
        f"  max power at 0<λ<1        = {metrics['power_max_below_lambda_one']:.3f}  rule ≥0.80 → "
        f"{'PASS' if metrics['power_rule_pass'] else 'FAIL'}\n"
        f"  CI<|ΔR| at λ=1            = {'PASS' if metrics['ci_vs_dr_pass'] else 'FAIL'}\n"
        f"  ledger                    = {out_path}\n"
        f"  verdict                   = {verdict}\n",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
