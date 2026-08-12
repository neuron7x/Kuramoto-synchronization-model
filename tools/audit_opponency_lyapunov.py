# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""N5 — Lyapunov stability certificate for the DA/5-HT opponency.

The allostatic regulator's clamp keeps the load in [-1, 1], but a clamp only
saturates a divergence — it does not prove the drive returns to equilibrium. This
certificate proves the underlying opponent-process ODE is globally asymptotically
stable, so the clamp is a safety margin, not the only thing preventing runaway.

For the REAL system matrix A (extracted from AllostaticRegulator._ode and verified
against its finite-difference Jacobian at the origin):

    A is Hurwitz               (all eigenvalues have negative real part)
    A^T P + P A = -Q  ⇒ P ≻ 0  (a quadratic Lyapunov function V(x)=x^T P x exists)
    dV/dt = -x^T Q x < 0        (V strictly decreases along trajectories)

plus an empirical contraction check driving the real regulator from a grid of
initial conditions with zero input: V decreases monotonically to equilibrium.
Emits a schema-bound certificate; an unstable verdict exits non-zero.
"""

from __future__ import annotations

import argparse
import json
import sys
from itertools import product
from pathlib import Path
from typing import Any

import numpy as np
from scipy.linalg import solve_continuous_lyapunov

from core.neuro.motivation import AllostaticRegulator

SCHEMA_ID = "geosync.opponency_lyapunov.v1"

# System matrix of the homogeneous opponent-process ODE (state = [allostatic,
# dopamine, stress]); the inputs (rpe, stress_input) are external and do not enter
# the stability matrix. Coefficients mirror AllostaticRegulator._ode and are
# verified against its Jacobian below.
_A = np.array(
    [
        [-0.1, 0.0, 0.2],
        [0.0, -0.2, 0.0],
        [0.0, 0.0, -0.1],
    ],
    dtype=float,
)


def _measured_jacobian() -> np.ndarray:
    """Finite-difference Jacobian of the REAL ODE at the origin (zero input)."""

    regulator = AllostaticRegulator()
    eps = 1e-6
    jac = np.zeros((3, 3), dtype=float)
    base = np.array(regulator._ode([0.0, 0.0, 0.0], 0.0, 0.0, 0.0), dtype=float)
    for j in range(3):
        y = [0.0, 0.0, 0.0]
        y[j] = eps
        perturbed = np.array(regulator._ode(y, 0.0, 0.0, 0.0), dtype=float)
        jac[:, j] = (perturbed - base) / eps
    return jac


def _empirical_contraction(p_matrix: np.ndarray) -> bool:
    """Drive the real regulator from a grid of ICs; V(x)=x^T P x must not grow."""

    grid = (-0.8, 0.0, 0.8)
    for a0, d0, s0 in product(grid, grid, grid):
        regulator = AllostaticRegulator()
        regulator.allostatic_load, regulator.dopamine_level, regulator.stress_level = a0, d0, s0
        state = np.array([a0, d0, s0], dtype=float)
        v_prev = float(state @ p_matrix @ state)
        for _ in range(50):
            regulator.update(0.0, 0.0)  # zero input -> relax to equilibrium
            state = np.array(
                [regulator.allostatic_load, regulator.dopamine_level, regulator.stress_level],
                dtype=float,
            )
            v_now = float(state @ p_matrix @ state)
            if v_now > v_prev + 1e-9:  # V must be non-increasing
                return False
            v_prev = v_now
    return True


def build_certificate() -> dict[str, Any]:
    """Compute and verify the Lyapunov stability certificate for the real ODE."""

    jacobian_matches = bool(np.allclose(_A, _measured_jacobian(), atol=1e-5))
    eigenvalues = np.linalg.eigvals(_A)
    hurwitz = bool(np.all(eigenvalues.real < 0.0))

    q_matrix = np.eye(3)
    # Solve A^T P + P A = -Q  ->  solve_continuous_lyapunov(A^T, -Q).
    p_matrix = solve_continuous_lyapunov(_A.T, -q_matrix)
    p_symmetric = 0.5 * (p_matrix + p_matrix.T)
    p_eigs = np.linalg.eigvalsh(p_symmetric)
    p_positive_definite = bool(np.all(p_eigs > 0.0))
    residual = _A.T @ p_matrix + p_matrix @ _A + q_matrix
    residual_ok = bool(np.allclose(residual, 0.0, atol=1e-8))
    contracts = _empirical_contraction(p_symmetric)

    checks = [
        {
            "id": "LYAP-1",
            "name": "system matrix matches the real ODE Jacobian",
            "holds": jacobian_matches,
        },
        {
            "id": "LYAP-2",
            "name": "A is Hurwitz (all eigenvalues have negative real part)",
            "holds": hurwitz,
        },
        {
            "id": "LYAP-3",
            "name": "Lyapunov solution P is positive definite",
            "holds": p_positive_definite,
        },
        {"id": "LYAP-4", "name": "A^T P + P A = -Q residual is zero", "holds": residual_ok},
        {
            "id": "LYAP-5",
            "name": "V(x)=x^T P x contracts from a grid of initial conditions",
            "holds": contracts,
        },
    ]
    verdict = "STABLE" if all(c["holds"] for c in checks) else "UNSTABLE"
    return {
        "schema": SCHEMA_ID,
        "component": "core.neuro.motivation.AllostaticRegulator (DA/5-HT opponent process)",
        "system_matrix": _A.tolist(),
        "eigenvalues_real": sorted(float(x) for x in eigenvalues.real),
        "p_min_eigenvalue": float(p_eigs.min()),
        "checks": checks,
        "gate": verdict,
        "verdict": "PASS" if verdict == "STABLE" else "FAIL",
    }


def exit_code(report: dict[str, Any], *, report_only: bool) -> int:
    if report["verdict"] == "FAIL" and not report_only:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Opponency Lyapunov stability certificate")
    p.add_argument("--out", help="write the certificate JSON here (else stdout)")
    p.add_argument("--report-only", action="store_true", help="always exit 0, mark report_only")
    args = p.parse_args(argv)

    report = build_certificate()
    report["report_only"] = bool(args.report_only)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    print(f"opponency stability: {report['gate']}", file=sys.stderr)
    return exit_code(report, report_only=bool(args.report_only))


if __name__ == "__main__":
    sys.exit(main())
