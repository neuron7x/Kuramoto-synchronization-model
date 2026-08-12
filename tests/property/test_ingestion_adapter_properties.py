# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Property tests validating ingestion adapter numeric stability."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pandas as pd
import pytest

try:
    from hypothesis import HealthCheck, given, settings
    from hypothesis import strategies as st
except ImportError:  # pragma: no cover
    pytest.skip("hypothesis not installed", allow_module_level=True)

from core.data.adapters import CSVIngestionAdapter, ParquetIngestionAdapter
from core.utils.dataframe_io import MissingParquetDependencyError, write_dataframe
from tests.tolerances import FLOAT_ABS_TOL, FLOAT_REL_TOL, TIMESTAMP_ABS_TOL


def _write_frame(rows: list[dict[str, float]], path: Path) -> None:
    frame = pd.DataFrame(rows)
    frame.to_csv(path, index=False)


float_strategy = st.floats(
    min_value=0.0001,
    max_value=1_000_000.0,
    allow_nan=False,
    allow_infinity=False,
)


@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    rows=st.lists(
        st.fixed_dictionaries(
            {
                "ts": st.floats(
                    min_value=0.0, max_value=2e9, allow_nan=False, allow_infinity=False
                ),
                "price": float_strategy,
                "volume": st.floats(
                    min_value=0.0,
                    max_value=10_000_000.0,
                    allow_nan=False,
                    allow_infinity=False,
                ),
            }
        ),
        min_size=1,
        max_size=25,
    )
)
def test_csv_adapter_preserves_numeric_precision(
    rows: list[dict[str, float]], tmp_path: Path
) -> None:
    """CSV ingestion should not introduce large rounding errors."""
    csv_path = tmp_path / "ticks.csv"
    _write_frame(rows, csv_path)

    adapter = CSVIngestionAdapter()
    ticks = asyncio.run(
        adapter.fetch(
            path=csv_path,
            symbol="BTCUSD",
            venue="BINANCE",
            timestamp_field="ts",
            price_field="price",
            volume_field="volume",
        )
    )

    assert len(ticks) == len(rows)
    for original, parsed in zip(rows, ticks, strict=False):
        assert parsed.symbol.replace("/", "").upper() == "BTCUSD"
        assert parsed.venue == "BINANCE"
        assert parsed.ts == pytest.approx(
            float(original["ts"]), rel=FLOAT_REL_TOL, abs=TIMESTAMP_ABS_TOL
        )
        assert float(parsed.price) == pytest.approx(
            float(original["price"]), rel=FLOAT_REL_TOL, abs=FLOAT_ABS_TOL
        )
        assert float(parsed.volume) == pytest.approx(
            float(original["volume"]), rel=FLOAT_REL_TOL, abs=FLOAT_ABS_TOL
        )


@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    rows=st.lists(
        st.fixed_dictionaries(
            {
                "ts": st.floats(
                    min_value=0.0, max_value=2e9, allow_nan=False, allow_infinity=False
                ),
                "price": float_strategy,
                "volume": st.floats(
                    min_value=0.0,
                    max_value=10_000_000.0,
                    allow_nan=False,
                    allow_infinity=False,
                ),
            }
        ),
        min_size=1,
        max_size=50,
    )
)
def test_parquet_adapter_matches_source_values(
    rows: list[dict[str, float]], tmp_path: Path
) -> None:
    """Parquet ingestion should match the source values within tolerance."""
    parquet_path = tmp_path / "ticks.parquet"
    frame = pd.DataFrame(rows)
    try:
        write_dataframe(frame, parquet_path, index=False)
    except MissingParquetDependencyError:
        pytest.skip("Parquet backend unavailable for property test")

    adapter = ParquetIngestionAdapter()
    ticks = asyncio.run(
        adapter.fetch(
            path=parquet_path,
            symbol="ETHUSD",
            venue="COINBASE",
            timestamp_field="ts",
            price_field="price",
            volume_field="volume",
        )
    )

    assert len(ticks) == len(rows)
    for original, parsed in zip(rows, ticks, strict=False):
        assert parsed.symbol.replace("/", "").upper() == "ETHUSD"
        assert parsed.venue == "COINBASE"
        assert parsed.ts == pytest.approx(
            float(original["ts"]), rel=FLOAT_REL_TOL, abs=TIMESTAMP_ABS_TOL
        )
        assert float(parsed.price) == pytest.approx(
            float(original["price"]), rel=FLOAT_REL_TOL, abs=FLOAT_ABS_TOL
        )
        assert float(parsed.volume) == pytest.approx(
            float(original["volume"]), rel=FLOAT_REL_TOL, abs=FLOAT_ABS_TOL
        )
