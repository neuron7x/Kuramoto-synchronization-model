# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests pinning the runtime binding of the verification-protocol kernel.

These lock the contract that ``governance.verification_protocol`` reads the
declared score weights, thresholds and conformance order *from the artifact* and
executes them fail-closed. If the kernel and the engine ever drift apart, or the
engine stops fail-closing on bad input, these fail.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from governance.verification_protocol import (
    DEFAULT_KERNEL_PATH,
    VerificationProtocol,
)

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "schemas"
    / "governance"
    / "neuron7x_verification_protocol.schema.json"
)


@pytest.fixture
def vp() -> VerificationProtocol:
    return VerificationProtocol.load()


def _write_kernel(tmp_path: Path, overrides: dict[str, object]) -> Path:
    base = json.loads(DEFAULT_KERNEL_PATH.read_text(encoding="utf-8"))
    base.update(overrides)
    out = tmp_path / "kernel.json"
    out.write_text(json.dumps(base), encoding="utf-8")
    return out


# ---------------------------------------------------------------------- schema
def test_real_kernel_is_schema_valid() -> None:
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft7Validator.check_schema(schema)
    kernel = json.loads(DEFAULT_KERNEL_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft7Validator(schema).validate(kernel)


# --------------------------------------------------------------------- loading
def test_loads_real_kernel_and_binds_declared_weights(vp: VerificationProtocol) -> None:
    assert vp.kernel_id == "neuron7x-verification-protocol-v2026-8"
    # The seven declared variables, parsed from the formula (not hardcoded).
    assert set(vp.variables) == {"R", "E", "C", "B", "F", "A", "L"}
    assert sum(w for _, w in vp.weights) == pytest.approx(1.0, abs=1e-9)


def test_thresholds_partition_unit_interval(vp: VerificationProtocol) -> None:
    bands = vp.thresholds
    assert bands[0].min == pytest.approx(0.0)
    assert bands[-1].max == pytest.approx(1.0)
    for lower, upper in zip(bands, bands[1:]):
        assert lower.max == pytest.approx(upper.min)


# ----------------------------------------------------------------------- score
def test_score_is_declared_weighted_sum(vp: VerificationProtocol) -> None:
    # Perfect proof on every axis -> K == 1.0 (weights sum to 1).
    full = dict.fromkeys(vp.variables, 1.0)
    assert vp.score(full) == pytest.approx(1.0)
    # Uniform half -> K == 0.5 regardless of the weight split.
    half = dict.fromkeys(vp.variables, 0.5)
    assert vp.score(half) == pytest.approx(0.5)


def test_score_matches_hand_computed_weighted_sum(vp: VerificationProtocol) -> None:
    weights = dict(vp.weights)
    subscores = {"R": 1.0, "E": 0.0, "C": 1.0, "B": 0.0, "F": 1.0, "A": 0.0, "L": 1.0}
    expected = sum(weights[k] * v for k, v in subscores.items())
    assert vp.score(subscores) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("k", "state"),
    [
        (0.0, "NON_CONFORMANT"),
        (0.34, "NON_CONFORMANT"),
        (0.35, "UNVERIFIED"),
        (0.54, "UNVERIFIED"),
        (0.55, "PARTIAL_CONFORMANCE"),
        (0.72, "LOCALLY_CONFORMANT"),
        (0.86, "CI_CONFORMANT"),
        (0.95, "EVIDENCE_CONFORMANT"),
        (1.0, "EVIDENCE_CONFORMANT"),
    ],
)
def test_quantize_matches_declared_thresholds(
    vp: VerificationProtocol, k: float, state: str
) -> None:
    assert vp.quantize(k) == state


# --------------------------------------------------------------- weakest link
def test_weakest_link_clamps_perfect_score(vp: VerificationProtocol) -> None:
    full = dict.fromkeys(vp.variables, 1.0)
    verdict = vp.evaluate(full, weakest_link_state="UNVERIFIED")
    assert verdict.raw_state == "EVIDENCE_CONFORMANT"
    assert verdict.final_state == "UNVERIFIED"
    assert verdict.clamped is True


def test_no_clamp_when_link_is_strong_enough(vp: VerificationProtocol) -> None:
    half = dict.fromkeys(vp.variables, 0.5)  # -> UNVERIFIED
    verdict = vp.evaluate(half, weakest_link_state="EVIDENCE_CONFORMANT")
    assert verdict.final_state == "UNVERIFIED"
    assert verdict.clamped is False


# ------------------------------------------------------------------ fail-closed
def test_subscore_out_of_range_rejected(vp: VerificationProtocol) -> None:
    bad = dict.fromkeys(vp.variables, 0.5)
    bad["R"] = 1.5
    with pytest.raises(ValueError, match="must lie in"):
        vp.score(bad)


def test_missing_subscore_rejected(vp: VerificationProtocol) -> None:
    partial = dict.fromkeys(vp.variables, 0.5)
    del partial["L"]
    with pytest.raises(ValueError, match="must cover exactly"):
        vp.score(partial)


def test_quantize_rejects_out_of_unit_interval(vp: VerificationProtocol) -> None:
    with pytest.raises(ValueError, match="must lie in"):
        vp.quantize(1.01)


def test_unknown_weakest_link_state_rejected(vp: VerificationProtocol) -> None:
    full = dict.fromkeys(vp.variables, 1.0)
    with pytest.raises(ValueError, match="unknown conformance state"):
        vp.evaluate(full, weakest_link_state="NOT_A_STATE")


def test_weights_not_summing_to_one_rejected(tmp_path: Path) -> None:
    bad = _write_kernel(
        tmp_path,
        {"score_function": {"formula": "K = 0.5R + 0.2E", "variables": {"R": "r", "E": "e"}}},
    )
    with pytest.raises(ValueError, match="sum to 1.0"):
        VerificationProtocol.load(bad)


def test_threshold_gap_rejected(tmp_path: Path) -> None:
    bad = _write_kernel(
        tmp_path,
        {
            "thresholds": [
                {"min": 0.0, "max": 0.4, "state": "NON_CONFORMANT"},
                {"min": 0.5, "max": 1.0, "state": "EVIDENCE_CONFORMANT"},
            ]
        },
    )
    with pytest.raises(ValueError, match="gap/overlap"):
        VerificationProtocol.load(bad)


def test_threshold_state_outside_conformance_states_rejected(tmp_path: Path) -> None:
    bad = _write_kernel(
        tmp_path,
        {"thresholds": [{"min": 0.0, "max": 1.0, "state": "MADE_UP_STATE"}]},
    )
    with pytest.raises(ValueError, match="not in conformance_states"):
        VerificationProtocol.load(bad)


def test_unreadable_kernel_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unreadable"):
        VerificationProtocol.load(tmp_path / "does_not_exist.json")
