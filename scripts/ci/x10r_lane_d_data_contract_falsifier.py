#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Falsifier driver for the Lane D data-contract acceptor (issue #1168).

Probes the fail-closed promise of ``validate_input_window`` empirically:

  1. the golden admissible window MUST validate and emit the pinned fingerprint;
  2. tampering that golden window (inject +Inf into a value) MUST be REJECTED
     with ``DataContractError``.

If the validator ever fails OPEN — i.e. it accepts the Inf-tampered window — this
script exits non-zero. A clean (admissible) input passing plus the tampered
input being rejected is the only success path; a non-zero exit means a fail-open
regression crept into the input-validation contract.

This is INPUT VALIDATION only. It asserts no market, predictive, or
product-readiness claim, and it emits no PRODUCT_READY verdict (§7 stop rule).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from research.reconstruction.data_contract import (
    DataContractError,
    validate_input_window,
)

_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "reconstruction"
    / "fixtures"
    / "golden_input_window.json"
)
# Public content hash (input fingerprint), not a credential.
_GOLDEN_FINGERPRINT = (
    "7dbdd5d1538bfe816bb0e0026a7238c29929851c3c717cfce7f994195e2219be"  # pragma: allowlist secret
)


def main() -> int:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    timestamps = np.asarray(payload["timestamps"], dtype=np.int64)
    values = np.asarray(payload["values"], dtype=np.float64)
    adjacency = np.asarray(payload["adjacency"], dtype=np.float64)

    # 1. Golden window must validate and emit the pinned fingerprint.
    contract = validate_input_window(timestamps=timestamps, values=values, adjacency=adjacency)
    if contract.input_fingerprint != _GOLDEN_FINGERPRINT:
        print(
            "FALSIFIER FAIL: golden fingerprint drift: "
            f"{contract.input_fingerprint} != {_GOLDEN_FINGERPRINT}",
            file=sys.stderr,
        )
        return 1

    # 2. Inf-tampered window must be rejected (fail-closed).
    tampered = values.copy()
    tampered[0] = np.inf
    try:
        validate_input_window(timestamps=timestamps, values=tampered, adjacency=adjacency)
    except DataContractError:
        print("x10r-lane-d-data-contract-falsifier-ok")
        return 0
    print(
        "FALSIFIER FAIL: validator accepted an Inf-tampered window (FAIL-OPEN).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
