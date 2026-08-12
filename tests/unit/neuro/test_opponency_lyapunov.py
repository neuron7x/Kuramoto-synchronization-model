# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""N5 — Lyapunov stability certificate for the DA/5-HT opponency (real ODE).

Defect-sensitive: the certificate's system matrix is verified against the real
AllostaticRegulator ODE Jacobian (change the ODE and LYAP-1 fails), and the
contraction check rejects a non-Lyapunov P (negative control). The certificate
proves the opponent process returns to equilibrium — the clamp is a margin, not
the only guard.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "tools" / "audit_opponency_lyapunov.py"
ARTIFACT = ROOT / "artifacts" / "neuro" / "opponency_lyapunov.json"
SCHEMA = ROOT / "audit" / "schema" / "opponency_lyapunov.schema.json"


def _load_tool():
    spec = importlib.util.spec_from_file_location("lyap", TOOL)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ly = _load_tool()


def test_certificate_is_stable() -> None:
    report = ly.build_certificate()
    assert report["gate"] == "STABLE"
    assert report["verdict"] == "PASS"
    assert all(c["holds"] for c in report["checks"])
    assert {c["id"] for c in report["checks"]} == {f"LYAP-{i}" for i in range(1, 6)}


def test_system_matrix_matches_real_ode_jacobian() -> None:
    # LYAP-1: the abstract A is the real controller's Jacobian at the origin.
    assert np.allclose(ly._A, ly._measured_jacobian(), atol=1e-5)


def test_matrix_is_hurwitz() -> None:
    eigenvalues = np.linalg.eigvals(ly._A)
    assert np.all(eigenvalues.real < 0.0)


def test_lyapunov_solution_is_positive_definite_with_zero_residual() -> None:
    from scipy.linalg import solve_continuous_lyapunov

    q = np.eye(3)
    p = solve_continuous_lyapunov(ly._A.T, -q)
    p_sym = 0.5 * (p + p.T)
    assert np.all(np.linalg.eigvalsh(p_sym) > 0.0)  # P > 0
    assert np.allclose(ly._A.T @ p + p @ ly._A + q, 0.0, atol=1e-8)  # A^T P + P A = -Q


def test_contraction_check_rejects_non_lyapunov_p() -> None:
    # Negative control: a negative-definite "P" is not a Lyapunov function, so the
    # contraction check must reject it (V would increase toward zero from below).
    assert ly._empirical_contraction(-np.eye(3)) is False


def test_contraction_holds_for_the_real_lyapunov_p() -> None:
    from scipy.linalg import solve_continuous_lyapunov

    p = solve_continuous_lyapunov(ly._A.T, -np.eye(3))
    assert ly._empirical_contraction(0.5 * (p + p.T)) is True


def test_exit_code_enforces_instability() -> None:
    assert ly.exit_code({"verdict": "PASS"}, report_only=False) == 0
    assert ly.exit_code({"verdict": "FAIL"}, report_only=False) == 1
    assert ly.exit_code({"verdict": "FAIL"}, report_only=True) == 0


def test_committed_certificate_is_schema_valid_and_stable() -> None:
    report = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert report["schema"] == ly.SCHEMA_ID
    assert report["gate"] == "STABLE" and report["verdict"] == "PASS"
    try:
        import jsonschema
    except ImportError:
        return
    jsonschema.validate(report, json.loads(SCHEMA.read_text(encoding="utf-8")))
