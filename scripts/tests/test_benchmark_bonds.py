# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import importlib
import sys
import types

import pytest


def _load_module(monkeypatch):
    dummy = types.ModuleType("runtime.thermo_controller")

    class DummyController:
        def __init__(self, *_, **__):
            pass

    dummy.ThermoController = DummyController
    monkeypatch.setitem(sys.modules, "runtime.thermo_controller", dummy)
    monkeypatch.setitem(
        sys.modules, "core.energy", types.SimpleNamespace(delta_free_energy=lambda a, b, c: 0.0)
    )
    return importlib.reload(importlib.import_module("scripts.benchmark_bonds"))


def test_main_passes_with_small_delta(monkeypatch) -> None:
    bench = _load_module(monkeypatch)
    monkeypatch.setattr(
        bench,
        "run_benchmark",
        lambda iterations=200: {"dFdt_mean": 0.0, "dFdt_min": 0.0, "dFdt_max": 0.0, "samples": 1},
    )
    monkeypatch.setattr(
        bench.argparse.ArgumentParser,
        "parse_args",
        lambda self: types.SimpleNamespace(target_dF=1e-10, iterations=10),
    )

    bench.main()  # should not raise


def test_main_exits_on_regression(monkeypatch) -> None:
    bench = _load_module(monkeypatch)
    monkeypatch.setattr(
        bench,
        "run_benchmark",
        lambda iterations=200: {"dFdt_mean": 5e-10, "dFdt_min": 0.0, "dFdt_max": 1.0, "samples": 3},
    )
    monkeypatch.setattr(
        bench.argparse.ArgumentParser,
        "parse_args",
        lambda self: types.SimpleNamespace(target_dF=1e-10, iterations=10),
    )

    with pytest.raises(SystemExit):
        bench.main()
