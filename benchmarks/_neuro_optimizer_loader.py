"""Helpers to load NeuroOptimizer without importing the entire package."""

from __future__ import annotations

import importlib.util
import sys
from functools import lru_cache
from pathlib import Path
from typing import Callable, Tuple, Type

import numpy as np


def load_optimizer() -> Tuple[Type[object], Type[object]]:
    """Load NeuroOptimizer and OptimizationConfig from the source file."""
    module_path = Path("src/tradepulse/core/neuro/neuro_optimizer.py")
    spec = importlib.util.spec_from_file_location("neuro_optimizer", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load neuro_optimizer module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.NeuroOptimizer, module.OptimizationConfig


def load_validation() -> Callable[..., None]:
    """Load validate_neuro_invariants from the source file."""
    module_path = Path("src/tradepulse/core/neuro/_validation.py")
    spec = importlib.util.spec_from_file_location("neuro_validation", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load neuro validation module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.validate_neuro_invariants


@lru_cache(maxsize=1)
def _stability_epsilon() -> float:
    _, optimization_config = load_optimizer()
    config = optimization_config()
    return float(config.numeric.stability_epsilon)


def compute_stability_score(history: list[float]) -> float:
    """Compute stability score using the optimizer's objective history."""
    if len(history) <= 10:
        return 0.5
    recent = np.asarray(history[-10:], dtype=float)
    mean_perf = np.mean(recent)
    denom = max(abs(mean_perf), _stability_epsilon())
    stability = 1.0 - (np.std(recent) / denom)
    return float(np.clip(stability, 0.0, 1.0))
