# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Characterization (golden) battery for validate_ohlcv.

validate_ohlcv is a cyclomatic-~29, 132-LOC sequence of data-integrity checks
(empty / min-rows / required column / NaN ratio / non-positive / constant /
OHLC relationships / volume). This battery freezes its observable output on a
corpus that exercises every branch, so the function can be decomposed into
per-check helpers with zero behaviour change. Each case locks the
``(valid, issues, warnings, nan_count, negative_count, row_count)`` tuple.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from core.data.validation import validate_ohlcv

_GOLDEN = json.loads((Path(__file__).with_name("validate_ohlcv_golden.json")).read_text())


def _frame(spec: dict[str, list[Any]]) -> pd.DataFrame:
    return pd.DataFrame({col: vals for col, vals in spec.items()})


def _capture(result: Any) -> dict[str, Any]:
    return {
        "valid": bool(result.valid),
        "issues": sorted(result.issues),
        "warnings": sorted(result.warnings),
        "nan_count": int(result.nan_count),
        "negative_count": int(result.negative_count),
        "row_count": int(result.row_count),
    }


@pytest.mark.parametrize("case", sorted(_GOLDEN))
def test_validate_ohlcv_matches_golden(case: str) -> None:
    entry = _GOLDEN[case]
    result = validate_ohlcv(_frame(entry["df"]))
    assert _capture(result) == entry["output"], (
        f"validate_ohlcv output changed for case '{case}' — the decomposition must "
        f"be behaviour-preserving. Regenerate the golden corpus only for an "
        f"intended validation-rule change."
    )


def test_corpus_exercises_invalid_frames() -> None:
    invalid = sum(1 for c in _GOLDEN.values() if not c["output"]["valid"])
    assert invalid >= 6, "characterization corpus lost its invalid-frame coverage"
