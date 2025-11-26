from __future__ import annotations

import pandas as pd
import pytest

from src.data.etl.monitoring import DistributionProfiler


def _summary_by_column(frame: pd.DataFrame, **profiler_kwargs):
    profiler = DistributionProfiler(**profiler_kwargs)
    summaries = profiler.profile(frame)
    return {summary.column: summary for summary in summaries}


def test_distribution_profiler_computes_rich_numeric_statistics() -> None:
    frame = pd.DataFrame(
        {
            "price": [1.0, 2.0, 3.5, 4.0, 5.5, None],
        }
    )

    summary = _summary_by_column(frame)["price"]
    numeric_series = frame["price"].dropna()

    assert summary.dtype == str(frame["price"].dtype)
    assert summary.count == len(frame)
    assert summary.nulls == 1
    assert summary.null_ratio == pytest.approx(1 / len(frame))
    assert summary.unique == numeric_series.nunique()
    assert summary.mean == pytest.approx(float(numeric_series.mean()))
    # pandas uses ddof=1 for std by default which matches the profiler.
    expected_std = float(numeric_series.std()) if len(numeric_series) > 1 else None
    if expected_std is None:
        assert summary.std is None
    else:
        assert summary.std == pytest.approx(expected_std)
    assert summary.min == pytest.approx(float(numeric_series.min()))
    assert summary.max == pytest.approx(float(numeric_series.max()))
    assert summary.median == pytest.approx(float(numeric_series.median()))

    expected_quantiles = {
        f"p{int(q * 100):02d}": float(numeric_series.quantile(q))
        for q in (0.05, 0.25, 0.5, 0.75, 0.95)
    }
    assert summary.quantiles is not None
    for key, value in expected_quantiles.items():
        assert summary.quantiles[key] == pytest.approx(value)

    assert summary.is_monotonic_increasing is True
    assert summary.is_monotonic_decreasing is False


def test_distribution_profiler_reports_top_values_for_categorical_data() -> None:
    frame = pd.DataFrame(
        {
            "status": ["ok", "fail", "ok", "ok", None, "pending", "pending"],
            "signals": [True, False, True, True, None, False, True],
        }
    )

    summaries = _summary_by_column(frame, max_top_values=2)
    status_summary = summaries["status"]
    signals_summary = summaries["signals"]

    assert status_summary.nulls == 1
    assert status_summary.null_ratio == pytest.approx(1 / len(frame))
    assert status_summary.unique == 3
    assert status_summary.mean is None
    assert status_summary.quantiles is None
    assert status_summary.top_values == [("ok", 3), ("pending", 2)]
    assert status_summary.is_monotonic_increasing is False
    assert status_summary.is_monotonic_decreasing is False

    # Boolean columns are treated as numeric for aggregation but still provide
    # useful frequency information.
    assert signals_summary.mean == pytest.approx(
        float(frame["signals"].dropna().mean())
    )
    assert signals_summary.top_values[0][0] is True
    assert signals_summary.top_values[0][1] == 4
