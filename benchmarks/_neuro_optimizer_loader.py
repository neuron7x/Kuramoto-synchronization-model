"""Helpers to load NeuroOptimizer without importing the entire package."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Tuple, Type


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
