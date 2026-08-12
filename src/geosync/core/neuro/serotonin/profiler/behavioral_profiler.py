# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Deprecated mirror. Canonical module lives at
``<repo>/core/neuro/serotonin/profiler/behavioral_profiler.py``.

We load that file by absolute path to avoid a circular import: the
pytest ``pythonpath = . src`` setting gives this mirror priority under
the dotted name ``core.neuro.serotonin.profiler.behavioral_profiler``,
so a plain ``from core... import ...`` would resolve back to this
file and self-reference its own partially-initialised module.
"""

from __future__ import annotations

import importlib.util as _importlib_util
import pathlib as _pathlib
import sys as _sys

_canonical_path = (
    _pathlib.Path(__file__).resolve().parents[6]
    / "core"
    / "neuro"
    / "serotonin"
    / "profiler"
    / "behavioral_profiler.py"
)

_spec = _importlib_util.spec_from_file_location(
    "_geosync_behavioral_profiler_canonical",
    _canonical_path,
)
assert (
    _spec is not None and _spec.loader is not None
), f"cannot locate canonical behavioral_profiler.py at {_canonical_path}"
_canonical_module = _importlib_util.module_from_spec(_spec)
_sys.modules[_spec.name] = _canonical_module
_spec.loader.exec_module(_canonical_module)

BehavioralProfile = _canonical_module.BehavioralProfile
ProfileStatistics = _canonical_module.ProfileStatistics
SerotoninProfiler = _canonical_module.SerotoninProfiler
TonicPhasicCharacteristics = _canonical_module.TonicPhasicCharacteristics
VetoCooldownCharacteristics = _canonical_module.VetoCooldownCharacteristics

__all__ = [
    "BehavioralProfile",
    "ProfileStatistics",
    "SerotoninProfiler",
    "TonicPhasicCharacteristics",
    "VetoCooldownCharacteristics",
]
