#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""X-10R CBS-loader falsifier driver (issue #639).

Proves two things, fail-closed, with a non-zero exit on any violation:

1. POSITIVE: the valid CBS fixture loads, yields a >= 2-node
   ``(s_out, s_in)`` pair with positive mass, and those marginals feed
   the SAME substrate-agnostic Cimini-Squartini engine to a finite
   fitness object (the acceptance path).

2. FALSIFIER (the teeth): the intragroup-violating fixture — which
   includes a ``reporter_group == counterparty_group`` row — MUST be
   rejected. CBS excludes intragroup positions by construction; a
   loader that silently accepted one would relabel LBS-style data as
   CBS. If ``load_cbs_marginals`` fails OPEN and accepts it, OR the CLI
   exits zero on it, this driver exits non-zero.

This is INPUT VALIDATION only — no market, predictive, alpha, or
bank-level inference claim is made or tested here.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from research.reconstruction.cimini_squartini import fit_cimini_squartini
from tools.build_bis_cbs_dataset import (
    CbsContractViolation,
    load_cbs_marginals,
    main,
)

_ROOT = Path(__file__).resolve().parents[2]

_FIXTURES = _ROOT / "tests" / "reconstruction" / "fixtures"
_VALID = _FIXTURES / "cbs_marginals_valid.json"
_INTRAGROUP = _FIXTURES / "cbs_marginals_intragroup_violation.json"


def _check_positive() -> None:
    marg = load_cbs_marginals(_VALID)
    if marg.n_nodes < 2:
        raise AssertionError(f"valid CBS fixture must yield >= 2 nodes; got {marg.n_nodes}")
    if not marg.intragroup_excluded:
        raise AssertionError("valid CBS fixture must report intragroup_excluded == True")
    if float(marg.s_out.sum()) <= 0.0 or float(marg.s_in.sum()) <= 0.0:
        raise AssertionError("valid CBS marginals must have positive out/in mass")
    fit = fit_cimini_squartini(marg.s_out, marg.s_in, target_density=0.20)
    if not (np.isfinite(fit.z) and fit.z >= 0.0):
        raise AssertionError(f"engine must return finite non-negative z; got {fit.z}")
    if fit.x.shape != (marg.n_nodes,) or fit.y.shape != (marg.n_nodes,):
        raise AssertionError("engine fitness vectors must align with CBS node count")


def _check_falsifier() -> None:
    # The loader must RAISE on the intragroup-including dataset.
    accepted = False
    try:
        load_cbs_marginals(_INTRAGROUP)
        accepted = True
    except CbsContractViolation:
        accepted = False
    if accepted:
        raise AssertionError(
            "FAIL-OPEN: loader accepted an intragroup CBS position; "
            "CBS excludes intragroup positions by construction (issue #639). "
            "This would relabel LBS-style data as CBS."
        )
    # The CLI must exit non-zero on the same dataset.
    rc = main(["--cbs-json", str(_INTRAGROUP)])
    if rc == 0:
        raise AssertionError(
            "FAIL-OPEN: CLI exited zero on an intragroup-including CBS dataset; "
            "expected non-zero (CBS ontology contract)."
        )
    # The CLI must exit zero on the valid dataset.
    rc_ok = main(["--cbs-json", str(_VALID)])
    if rc_ok != 0:
        raise AssertionError(f"valid CBS dataset must exit zero; got {rc_ok}")


def main_driver() -> int:
    _check_positive()
    _check_falsifier()
    print(
        "PASS: X-10R CBS loader falsifier — valid fixture loads + feeds engine; intragroup rejected."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main_driver())
