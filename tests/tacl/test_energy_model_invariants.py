# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Invariant-focused tests for the TACL energy model."""

from __future__ import annotations

import pytest

from tacl.energy_model import DEFAULT_THRESHOLDS, EnergyMetrics, EnergyModel


def _metrics_from_thresholds(overrides: dict[str, float] | None = None) -> EnergyMetrics:
    values = {name: float(value) for name, value in DEFAULT_THRESHOLDS.items()}
    if overrides:
        values.update({name: float(value) for name, value in overrides.items()})
    return EnergyMetrics(
        latency_p95=values["latency_p95"],
        latency_p99=values["latency_p99"],
        coherency_drift=values["coherency_drift"],
        cpu_burn=values["cpu_burn"],
        mem_cost=values["mem_cost"],
        queue_depth=values["queue_depth"],
        packet_loss=values["packet_loss"],
    )


def test_internal_energy_uses_normalized_weights() -> None:
    thresholds = DEFAULT_THRESHOLDS
    weights = {
        "latency_p95": 1.0,
        "latency_p99": 3.0,
        "coherency_drift": 1.0,
        "cpu_burn": 1.0,
        "mem_cost": 1.0,
        "queue_depth": 1.0,
        "packet_loss": 1.0,
    }
    model = EnergyModel(
        thresholds=thresholds,
        weights=weights,
        base_internal_energy=0.5,
        temperature=0.4,
        entropy_floor=0.05,
    )
    metrics = _metrics_from_thresholds(
        {
            "latency_p95": thresholds["latency_p95"] * 1.1,
            "latency_p99": thresholds["latency_p99"] * 1.2,
        }
    )

    penalties = model.diagnostics(metrics)
    expected_penalty_p95 = 0.1
    expected_penalty_p99 = 0.2
    assert penalties["latency_p95"] == pytest.approx(expected_penalty_p95)
    assert penalties["latency_p99"] == pytest.approx(expected_penalty_p99)

    total_weight = sum(weights.values())
    expected_internal = 0.5 + (
        expected_penalty_p95 * (weights["latency_p95"] / total_weight)
        + expected_penalty_p99 * (weights["latency_p99"] / total_weight)
    )
    assert model.internal_energy(metrics) == pytest.approx(expected_internal)


def test_entropy_floor_applies_when_all_metrics_exceed_thresholds() -> None:
    model = EnergyModel(entropy_floor=0.12)
    metrics = _metrics_from_thresholds(
        {name: value * 2.0 for name, value in DEFAULT_THRESHOLDS.items()}
    )
    entropy = model.entropy(metrics)
    assert entropy == pytest.approx(0.12)


def test_evaluate_reports_reason_when_free_energy_exceeds_bound() -> None:
    model = EnergyModel(base_internal_energy=1.5, temperature=0.1)
    metrics = _metrics_from_thresholds()
    result = model.evaluate(metrics, max_free_energy=0.5)
    assert result.passed is False
    assert result.reason is not None
    assert "free energy" in result.reason
