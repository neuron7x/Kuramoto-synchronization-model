#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Falsifier driver for the D-002A Gate 6 sensitivity-surface acceptor.

Extracted verbatim from the inline ``python -c`` payload of
``.claude/commit_acceptors/x10r-gate6-sensitivity-surface.yaml``. The original
inline program could not survive the commit-acceptor YAML round-trip: it was
authored inside a folded (``>``) block scalar, which collapsed its newlines
into spaces (turning multi-statement source into a ``SyntaxError``), and its
Python string literals used single quotes that lived inside the outer
``bash -c '...'`` single-quoted wrapper — each one prematurely closed the bash
quote. A committed single-purpose script invoked by name is round-trip-stable
and is the convention used elsewhere (see ``gauss_bonnet_evidence.py``).

This module is a faithful restoration of that probe — no statement, assertion,
bound, or message has been added, removed, or altered. It probes the D-002A
pilot contract empirically at the pilot budget (N=50, n_seeds=5, n_bootstrap=4):
the surface must compute end-to-end for lambda in {0, 1}, report a finite
fpr_estimate <= 0.30 (fail-closed), populate the MDE dict (None/inf permitted
as the honest sub-MDE state), and survive JSON inf->None serialisation. NO power
assertion is made — power certification is the D-002B contract (issue #652).
A non-zero exit means the D-002A infrastructure or fail-closed pilot envelope
regressed.
"""

import math

from research.reconstruction.sensitivity_surface import (
    compute_sensitivity_surface,
)

s = compute_sensitivity_surface(
    n_grid=(50,),
    lambda_grid=(0.0, 1.0),
    n_seeds=5,
    n_bootstrap=4,
)
zero = s.cell(n=50, lambda_mix=0.0)
one = s.cell(n=50, lambda_mix=1.0)
assert zero is not None, "lambda=0 cell missing"
assert one is not None, "lambda=1 cell missing"
assert math.isfinite(s.fpr_estimate), "fpr_estimate not finite"
assert s.fpr_estimate <= 0.30, f"pilot fail-closed broken: FPR={s.fpr_estimate:.3f} > 0.30"
mde = s.mde_lambda_per_n.get(50)
assert mde is not None, "MDE key missing for N=50"
payload = s.to_dict()
assert len(payload["cells"]) == 2, "cell serialisation lost cells"
serialised_mde = payload["mde_lambda_per_n"][50]
assert serialised_mde is None or isinstance(serialised_mde, float), "inf→None coercion broken"
