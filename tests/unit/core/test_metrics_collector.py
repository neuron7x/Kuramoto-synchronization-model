# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import pytest

from core.utils import metrics


@pytest.mark.skipif(not metrics.PROMETHEUS_AVAILABLE, reason="prometheus_client is not installed")
def test_get_metrics_collector_reinitialises_for_new_registry(monkeypatch):
    from prometheus_client import CollectorRegistry

    # Ensure a clean slate for the global collector
    monkeypatch.setattr(metrics, "_collector", None)

    first_registry = CollectorRegistry()
    first_collector = metrics.get_metrics_collector(first_registry)

    second_registry = CollectorRegistry()
    second_collector = metrics.get_metrics_collector(second_registry)

    assert first_collector.registry is first_registry
    assert second_collector.registry is second_registry
    assert second_collector is not first_collector
