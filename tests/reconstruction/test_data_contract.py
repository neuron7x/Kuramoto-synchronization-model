# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the Lane D input-window data contract (issue #1168).

These tests cover INPUT VALIDATION only. They assert the validator fails closed
on inadmissible windows and emits a stable fingerprint on the golden admissible
window. They make NO market, predictive, or product-readiness claim, and there
is intentionally no PRODUCT_READY verdict anywhere in this slice (§7 stop rule).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from research.reconstruction.data_contract import (
    DataContractError,
    InputWindowContract,
    validate_input_window,
)

_FIXTURE = Path(__file__).parent / "fixtures" / "golden_input_window.json"

# Pinned expected fingerprint of the golden admissible window. If the validator's
# canonicalisation changes, this hash must change too — that is the point: the
# fingerprint is a contract, not an incidental value.
# pragma: allowlist secret — public content hash (input fingerprint), not a credential.
_GOLDEN_FINGERPRINT = (
    "7dbdd5d1538bfe816bb0e0026a7238c29929851c3c717cfce7f994195e2219be"  # pragma: allowlist secret
)


def _load_golden() -> dict[str, Any]:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _golden_arrays() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    g = _load_golden()
    ts = np.asarray(g["timestamps"], dtype=np.int64)
    vals = np.asarray(g["values"], dtype=np.float64)
    adj = np.asarray(g["adjacency"], dtype=np.float64)
    return ts, vals, adj


# ---------------------------------------------------------------------------
# Golden (admissible) path
# ---------------------------------------------------------------------------


def test_golden_window_passes_and_returns_contract() -> None:
    ts, vals, adj = _golden_arrays()
    contract = validate_input_window(timestamps=ts, values=vals, adjacency=adj)
    assert isinstance(contract, InputWindowContract)
    assert contract.n_nodes == 4
    assert contract.has_adjacency is True


def test_golden_fingerprint_is_stable_and_pinned() -> None:
    ts, vals, adj = _golden_arrays()
    a = validate_input_window(timestamps=ts, values=vals, adjacency=adj)
    b = validate_input_window(timestamps=ts.copy(), values=vals.copy(), adjacency=adj.copy())
    # Determinism across calls.
    assert a.input_fingerprint == b.input_fingerprint
    # Pinned hash — a canonicalisation change must surface here.
    assert a.input_fingerprint == _GOLDEN_FINGERPRINT
    assert len(a.input_fingerprint) == 64
    assert int(a.input_fingerprint, 16) >= 0  # valid lowercase hex


def test_window_without_adjacency_is_admissible() -> None:
    ts, vals, _ = _golden_arrays()
    contract = validate_input_window(timestamps=ts, values=vals)
    assert contract.has_adjacency is False
    # Distinct fingerprint from the with-adjacency window (adjacency is tagged).
    full = validate_input_window(timestamps=ts, values=vals, adjacency=_golden_arrays()[2])
    assert contract.input_fingerprint != full.input_fingerprint


def test_perturbed_value_changes_fingerprint() -> None:
    ts, vals, adj = _golden_arrays()
    base = validate_input_window(timestamps=ts, values=vals, adjacency=adj)
    tampered = vals.copy()
    tampered[0] += 0.001  # above the 1e-9 rounding quantum
    perturbed = validate_input_window(timestamps=ts, values=tampered, adjacency=adj)
    assert perturbed.input_fingerprint != base.input_fingerprint


# ---------------------------------------------------------------------------
# Fail-closed (inadmissible) paths
# ---------------------------------------------------------------------------


def test_nan_value_rejected() -> None:
    ts, vals, adj = _golden_arrays()
    bad = vals.copy()
    bad[2] = np.nan
    with pytest.raises(DataContractError, match="finite"):
        validate_input_window(timestamps=ts, values=bad, adjacency=adj)


def test_inf_value_rejected() -> None:
    ts, vals, adj = _golden_arrays()
    bad = vals.copy()
    bad[1] = np.inf
    with pytest.raises(DataContractError, match="finite"):
        validate_input_window(timestamps=ts, values=bad, adjacency=adj)


def test_non_monotonic_timestamps_rejected() -> None:
    ts, vals, adj = _golden_arrays()
    bad = ts.copy()
    bad[2] = bad[1]  # equal -> not strictly increasing
    with pytest.raises(DataContractError, match="monotonic"):
        validate_input_window(timestamps=bad, values=vals, adjacency=adj)


def test_decreasing_timestamps_rejected() -> None:
    ts, vals, adj = _golden_arrays()
    bad = ts[::-1].copy()
    with pytest.raises(DataContractError, match="monotonic"):
        validate_input_window(timestamps=bad, values=vals, adjacency=adj)


def test_float_timestamps_rejected() -> None:
    ts, vals, adj = _golden_arrays()
    with pytest.raises(DataContractError, match="integer-typed"):
        validate_input_window(
            timestamps=ts.astype(np.float64), values=vals, adjacency=adj
        )


def test_timestamp_length_mismatch_rejected() -> None:
    ts, vals, adj = _golden_arrays()
    with pytest.raises(DataContractError, match="length"):
        validate_input_window(timestamps=ts[:-1], values=vals, adjacency=adj)


def test_empty_graph_rejected() -> None:
    with pytest.raises(DataContractError, match="empty/degenerate"):
        validate_input_window(
            timestamps=np.asarray([1], dtype=np.int64),
            values=np.asarray([1.0], dtype=np.float64),
        )


def test_non_square_adjacency_rejected() -> None:
    ts, vals, _ = _golden_arrays()
    bad = np.zeros((4, 3), dtype=np.float64)
    with pytest.raises(DataContractError, match="square"):
        validate_input_window(timestamps=ts, values=vals, adjacency=bad)


def test_adjacency_shape_mismatch_rejected() -> None:
    ts, vals, _ = _golden_arrays()
    bad = np.zeros((3, 3), dtype=np.float64)
    with pytest.raises(DataContractError, match="node count"):
        validate_input_window(timestamps=ts, values=vals, adjacency=bad)


def test_negative_adjacency_rejected() -> None:
    ts, vals, adj = _golden_arrays()
    bad = adj.copy()
    bad[0, 1] = -0.5
    bad[1, 0] = -0.5
    with pytest.raises(DataContractError, match="non-negative"):
        validate_input_window(timestamps=ts, values=vals, adjacency=bad)


def test_self_loop_adjacency_rejected() -> None:
    ts, vals, adj = _golden_arrays()
    bad = adj.copy()
    bad[0, 0] = 0.7
    with pytest.raises(DataContractError, match="self-loops"):
        validate_input_window(timestamps=ts, values=vals, adjacency=bad)


def test_nan_adjacency_rejected() -> None:
    ts, vals, adj = _golden_arrays()
    bad = adj.copy()
    bad[2, 3] = np.nan
    bad[3, 2] = np.nan
    with pytest.raises(DataContractError, match="finite"):
        validate_input_window(timestamps=ts, values=vals, adjacency=bad)


def test_data_contract_error_is_value_error() -> None:
    # Existing fail-closed call sites that catch ValueError keep working.
    assert issubclass(DataContractError, ValueError)


# ---------------------------------------------------------------------------
# Falsifier: tampering the golden fixture (inject Inf) MUST be rejected.
# This guards against a fail-open regression in the validator.
# ---------------------------------------------------------------------------


def test_falsifier_inf_injection_into_golden_is_rejected() -> None:
    ts, vals, adj = _golden_arrays()
    tampered = vals.copy()
    tampered[0] = np.inf
    with pytest.raises(DataContractError):
        validate_input_window(timestamps=ts, values=tampered, adjacency=adj)
