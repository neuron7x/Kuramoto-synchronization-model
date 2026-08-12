# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import importlib
import json
from pathlib import Path

import scripts.validate_metrics as vm


def _reload_with_artifacts(tmp_path: Path) -> None:
    import os

    os.environ["METRICS_VALIDATION_ARTIFACT_DIR"] = str(tmp_path / "artifacts")
    importlib.reload(vm)


def test_runtime_semantics_produce_deltas(tmp_path: Path) -> None:
    _reload_with_artifacts(tmp_path)
    root = Path(__file__).resolve().parents[2]
    catalogs = [root / "observability" / "metrics.json"]

    status = vm.run_runtime(root, catalogs)
    assert status == 0

    artifact = Path(vm.ARTIFACT_DIR) / "runtime.json"
    payload = json.loads(artifact.read_text(encoding="utf-8"))

    deltas = payload["metric_deltas"]
    invariants = payload["invariants"]

    assert deltas["geosync_api_requests_total"] is None or deltas["geosync_api_requests_total"] >= 2
    assert invariants["health_counter_incremented"]
    assert invariants["health_latency_incremented"]
    assert invariants["latency_finite"]
    assert invariants["inflight_finite"]
    assert invariants["queue_depth_finite"]
    assert invariants["non_api_metric_delta"]
