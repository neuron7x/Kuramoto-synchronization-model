# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Narrow pandas datetime guard for research integrity gates.

The Research Integrity Gate exposed a CPython-level segmentation fault in
``pandas.to_datetime`` while Protocol X-9R converted a parquet-roundtripped
``Series`` of ``datetime.date`` values inside the leakage sentinel. A crash at
that layer is not an acceptable fail-closed outcome: it hides the protocol gate
verdict and prevents the research integrity surface from reporting evidence.

This guard is intentionally narrow. It only bypasses pandas' C-extension
conversion path for a pandas ``Series`` whose non-null values are already Python
``date``/``datetime`` instances and where no extra ``to_datetime`` arguments are
provided. All other inputs are delegated to pandas unchanged.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from typing import Any

import pandas as pd

_ORIGINAL_TO_DATETIME: Callable[..., Any] = pd.to_datetime
_INSTALLED = False


def _is_plain_date_like(value: object) -> bool:
    return isinstance(value, (date, datetime))


def _is_supported_date_series(value: object) -> bool:
    if not isinstance(value, pd.Series):
        return False
    return all(v is None or v is pd.NaT or _is_plain_date_like(v) for v in value.to_list())


def _convert_date_series(value: pd.Series) -> pd.Series:
    converted = []
    for item in value.to_list():
        if item is None or item is pd.NaT:
            converted.append(pd.NaT)
        else:
            converted.append(pd.Timestamp(item))
    return pd.Series(converted, index=value.index, name=value.name)


def install_safe_to_datetime_guard() -> None:
    """Install a process-local, idempotent guard around ``pandas.to_datetime``."""

    global _INSTALLED
    if _INSTALLED:
        return

    def guarded_to_datetime(arg: Any, *args: Any, **kwargs: Any) -> Any:
        if not args and not kwargs and _is_supported_date_series(arg):
            return _convert_date_series(arg)
        return _ORIGINAL_TO_DATETIME(arg, *args, **kwargs)

    setattr(pd, "to_datetime", guarded_to_datetime)
    _INSTALLED = True
