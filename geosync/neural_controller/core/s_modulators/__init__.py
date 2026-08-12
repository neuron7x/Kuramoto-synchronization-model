# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import importlib
import pkgutil
from typing import Callable, Iterable

SModulator = Callable[[object, dict[str, float]], float]


def load_s_modulators() -> list[SModulator]:
    modulators: list[SModulator] = []
    for module_info in _iter_modules():
        module = importlib.import_module(f"{__name__}.{module_info}")
        modulator = getattr(module, "modulator", None) or getattr(module, "MODULATOR", None)
        if modulator is None:
            raise AttributeError(f"S modulator module '{module.__name__}' must define 'modulator'")
        modulators.append(modulator)
    return modulators


def _iter_modules() -> Iterable[str]:
    for module_info in pkgutil.iter_modules(__path__):
        if module_info.name.startswith("_"):
            continue
        yield module_info.name
