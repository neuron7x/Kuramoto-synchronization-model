# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Regression lock for the namespace-policy repair (audit T5).

Three standalone-package shims used to import a top-level ``src.*`` that no
longer existed — they were both a namespace violation and broken (ImportError).
They were repaired to fully-qualified local-src imports. These tests prove the
repair holds: the shims import, and the canonical-namespace gate stays green.
"""

from __future__ import annotations

import importlib

import pytest

SHIMS = [
    "analytics.fpma.geosync_fpma",
    "analytics.regime.geosync_regime",
    "markets.orderbook.geosync_orderbook",
]


@pytest.mark.parametrize("module_name", SHIMS)
def test_repaired_shim_imports(module_name: str) -> None:
    # Previously raised ImportError (from src.core / from src import …).
    module = importlib.import_module(module_name)
    assert module.__name__ == module_name


def test_namespace_policy_gate_passes() -> None:
    import importlib.util
    import sys
    from pathlib import Path

    gate_path = Path(__file__).resolve().parents[3] / "scripts" / "check_namespace_policy.py"
    spec = importlib.util.spec_from_file_location("check_namespace_policy", gate_path)
    assert spec is not None and spec.loader is not None
    gate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = gate  # dataclasses need the module registered before exec
    spec.loader.exec_module(gate)
    assert gate.main() == 0
