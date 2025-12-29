from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path

import pytest


def _install_stub_modules(monkeypatch) -> None:
    dummy = types.ModuleType("dummy")
    dummy.walk_forward = lambda *a, **k: None
    monkeypatch.setitem(sys.modules, "backtest.engine", dummy)

    strategy_mod = types.ModuleType("strategy")
    strategy_mod.Strategy = type(
        "Strategy", (), {"__init__": lambda self, *a, **k: None, "simulate_performance": lambda self, frame: None}
    )
    monkeypatch.setitem(sys.modules, "core.agent.strategy", strategy_mod)

    preprocess_mod = types.ModuleType("preprocess")
    preprocess_mod.normalize_df = lambda frame: frame
    preprocess_mod.scale_series = lambda data, method="zscore": data
    monkeypatch.setitem(sys.modules, "core.data.preprocess", preprocess_mod)

    entropy_mod = types.ModuleType("entropy")
    entropy_mod.EntropyFeature = type("EntropyFeature", (), {})
    monkeypatch.setitem(sys.modules, "core.indicators.entropy", entropy_mod)

    hier_mod = types.ModuleType("hierarchical")
    hier_mod.FeatureBufferCache = type("FeatureBufferCache", (), {})
    hier_mod.compute_hierarchical_features = lambda *a, **k: None
    monkeypatch.setitem(sys.modules, "core.indicators.hierarchical_features", hier_mod)

    hurst_mod = types.ModuleType("hurst")
    hurst_mod.HurstFeature = type("HurstFeature", (), {})
    monkeypatch.setitem(sys.modules, "core.indicators.hurst", hurst_mod)

    kuramoto_mod = types.ModuleType("kuramoto")
    kuramoto_mod.KuramotoOrderFeature = type("KuramotoOrderFeature", (), {})
    kuramoto_mod.compute_phase = lambda *a, **k: None
    kuramoto_mod.kuramoto_order = lambda *a, **k: None
    monkeypatch.setitem(sys.modules, "core.indicators.kuramoto", kuramoto_mod)

    pipeline_mod = types.ModuleType("pipeline")

    class DummyPipeline:
        def __init__(self, *_, **__):
            pass

        def run(self, data):
            return types.SimpleNamespace(release=lambda: None)

    pipeline_mod.IndicatorPipeline = DummyPipeline
    monkeypatch.setitem(sys.modules, "core.indicators.pipeline", pipeline_mod)

    class DummyRNG:
        def normal(self, *_, **__):
            return [0.0]

        def uniform(self, *_, **__):
            return [[0.0]]

        def astype(self, *_, **__):
            return [0.0]

    numpy_mod = types.ModuleType("numpy")
    numpy_mod.random = types.SimpleNamespace(default_rng=lambda seed=None: DummyRNG())
    numpy_mod.linspace = lambda *a, **k: [0.0]
    numpy_mod.cumsum = lambda arr: arr
    monkeypatch.setitem(sys.modules, "numpy", numpy_mod)

    pandas_mod = types.ModuleType("pandas")
    pandas_mod.DataFrame = lambda *a, **k: object()
    pandas_mod.date_range = lambda *a, **k: []
    monkeypatch.setitem(sys.modules, "pandas", pandas_mod)


def test_main_writes_payload(tmp_path: Path, monkeypatch) -> None:
    _install_stub_modules(monkeypatch)
    mod = importlib.import_module("scripts.performance.run_resource_checks")

    output = tmp_path / "metrics.json"
    monkeypatch.setattr(
        mod, "_parse_args", lambda: types.SimpleNamespace(output=output)
    )
    metric = mod.Metric(
        name="demo", value=1.0, unit="bytes", category="memory", budget=2.0
    )
    monkeypatch.setattr(mod, "collect_metrics", lambda: [metric])

    mod.main()

    payload = json.loads(output.read_text())
    assert payload["metrics"][0]["name"] == "demo"
    assert payload["metrics"][0]["value"] >= 0
    assert payload["metrics"][0]["category"] == "memory"


def test_main_failure_when_output_parent_invalid(tmp_path: Path, monkeypatch) -> None:
    _install_stub_modules(monkeypatch)
    mod = importlib.import_module("scripts.performance.run_resource_checks")

    blocker = tmp_path / "blocked"
    blocker.write_text("file")
    output = blocker / "out.json"
    monkeypatch.setattr(
        mod, "_parse_args", lambda: types.SimpleNamespace(output=output)
    )
    monkeypatch.setattr(mod, "collect_metrics", lambda: [])

    with pytest.raises(FileExistsError):
        mod.main()
