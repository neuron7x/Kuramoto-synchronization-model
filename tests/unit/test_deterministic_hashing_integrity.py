# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Regression: determinism of tamper-evident / dedup hashing surfaces.

Covers three defects found in a round-2 adversarial sweep:
  * order_ledger._coerce leaked salted set-iteration order into the state hash;
  * idempotency.keys did not canonicalize floats (-0.0 vs +0.0 → different key)
    and emitted non-standard JSON for NaN/Inf;
  * ofi_unity_live silently measured IC against a price level when the return
    column was absent.

`execution.*` is behind the forbidden_import_patterns gate, so order_ledger is
loaded via importlib (the repo-sanctioned pattern).
"""

from __future__ import annotations

import importlib
import json

import pytest

from core.idempotency.keys import canonical_dumps, fingerprint_payload

_order_ledger = importlib.import_module("execution.order_ledger")
_coerce = _order_ledger._coerce


# --------------------------------------------------------------------------- #
# order_ledger._coerce — sets must serialize in a stable, sorted order
# --------------------------------------------------------------------------- #
def test_coerce_set_is_sorted_and_order_independent() -> None:
    a = _coerce({"tags": {"gamma", "alpha", "beta", "delta", "omega"}})
    b = _coerce({"tags": {"omega", "delta", "beta", "alpha", "gamma"}})
    assert a == b  # identical logical set → identical serialization
    assert a["tags"] == sorted(a["tags"])  # deterministic (sorted) order


def test_coerce_list_order_is_preserved() -> None:
    # Lists are ordered — must NOT be sorted (only sets are).
    assert _coerce(["c", "a", "b"]) == ["c", "a", "b"]


# --------------------------------------------------------------------------- #
# idempotency.keys — float canonicalization
# --------------------------------------------------------------------------- #
def test_negative_zero_fingerprints_identically_to_positive_zero() -> None:
    assert fingerprint_payload({"px": -0.0}) == fingerprint_payload({"px": 0.0})


def test_non_finite_float_is_rejected() -> None:
    with pytest.raises(ValueError):
        canonical_dumps({"x": float("nan")})
    with pytest.raises(ValueError):
        fingerprint_payload({"x": float("inf")})


def test_ordinary_floats_are_unchanged() -> None:
    # Sanity: the canonicalization must not perturb normal values.
    assert json.loads(canonical_dumps({"px": 1.25}))["px"] == 1.25


# --------------------------------------------------------------------------- #
# ofi_unity_live — require the return column, fail loud not silent
# --------------------------------------------------------------------------- #
def test_ofi_unity_requires_mid_returns_column(tmp_path) -> None:
    ofi = importlib.import_module("research.kernels.ofi_unity_live")
    csv = tmp_path / "no_returns.csv"
    csv.write_text("ts,bid_close,ask_close\n1,10.0,10.2\n2,10.1,10.3\n3,10.2,10.4\n")
    verdict = ofi.run(source="test", input_csv=csv, output=tmp_path / "out.json")
    assert verdict["FINAL"] == "REJECT"
    assert "mid_returns" in verdict["reason"]
