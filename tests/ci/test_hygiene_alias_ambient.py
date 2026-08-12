# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Regression battery for V7: aliased-ambient detection in check_code_hygiene.

The ambient-nondeterminism detector matches on the trailing dotted components
of a call target. Before V7, an *aliased* import evaded it
(``import datetime as DT; DT.now()`` -> base ``DT`` never matched). V7 resolves
the call's base name through the file's import-alias map first. These tests pin
that aliased ambient calls are caught and non-ambient calls are not.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MOD = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "check_code_hygiene.py"
_spec = importlib.util.spec_from_file_location("check_code_hygiene", _MOD)
assert _spec and _spec.loader
_m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_m)

_THR = {"max_function_loc": 80, "max_class_loc": 400, "max_complexity": 15, "max_file_loc": 800}


def _ambient(src: str) -> int:
    _syms, counts = _m._scan_file("t.py", src, _THR)
    return counts["ambient_nondeterminism"]


def test_aliased_module_clock_is_caught() -> None:
    assert _ambient("import datetime as DT\ndef f():\n    return DT.now()\n") == 1


def test_aliased_from_import_clock_is_caught() -> None:
    assert _ambient("from time import time as t\ndef f():\n    return t()\n") == 1


def test_aliased_rng_is_caught() -> None:
    assert _ambient("import numpy.random as npr\ndef f():\n    return npr.default_rng()\n") == 1


def test_from_import_aliased_datetime_is_caught() -> None:
    assert _ambient("from datetime import datetime as DT\ndef f():\n    return DT.now()\n") == 1


def test_non_ambient_aliased_call_is_not_counted() -> None:
    assert _ambient("import os as o\ndef f():\n    return o.getpid()\n") == 0


def test_unaliased_ambient_still_caught() -> None:
    # the original suffix path must keep working
    assert _ambient("import time\ndef f():\n    return time.time()\n") == 1
