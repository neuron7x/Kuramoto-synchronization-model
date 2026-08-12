from __future__ import annotations

from geosync.core.neuro.dopamine.telemetry import (
    METRIC_NAMES,
    bounded_value,
    bounded_value_delta,
    metric_catalog,
)


def test_metric_catalog_contains_required_sli_names() -> None:
    catalog = metric_catalog()
    assert len(METRIC_NAMES) == 16
    assert "dopamine.rpe_finite_rate" in catalog
    assert "dopamine.p99_step_latency_ms" in catalog
    assert "dopamine.cognitive_value_score" in catalog
    assert all(spec["owner"] == "geosync.dopamine" for spec in catalog.values())


def test_bounded_value_orders_useful_states() -> None:
    low = bounded_value(0.1, 0.1, 0.1, 0.1)
    high = bounded_value(0.9, 0.9, 0.8, 0.7)
    assert 0.0 <= low <= 1.0
    assert 0.0 <= high <= 1.0
    assert high > low


def test_bounded_value_delta_controls_priority_direction() -> None:
    positive = bounded_value_delta(0.1, 0.8)
    negative = bounded_value_delta(0.8, 0.1)
    assert positive["bounded_rpe"] > 0.0
    assert positive["priority"] > 0.5
    assert negative["bounded_rpe"] < 0.0
    assert negative["priority"] < 0.5
