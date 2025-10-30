# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Fuzz tests for data ingestion with malformed, edge case, and corrupted data."""
from __future__ import annotations

import csv
import math
from decimal import Decimal
from pathlib import Path

import pytest

try:
    from hypothesis import HealthCheck, given, settings
    from hypothesis import strategies as st
except ImportError:  # pragma: no cover
    pytest.skip("hypothesis not installed", allow_module_level=True)

from core.data.ingestion import DataIngestor, Ticker
from tests.tolerances import FLOAT_ABS_TOL, FLOAT_REL_TOL


class TestCSVFuzzTests:
    """Fuzz tests for CSV data ingestion."""

    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        rows=st.lists(
            st.fixed_dictionaries(
                {
                    "ts": st.one_of(
                        st.floats(
                            min_value=0.0,
                            max_value=2e9,
                            allow_nan=False,
                            allow_infinity=False,
                        ),
                        st.just("invalid"),
                        st.just(""),
                    ),
                    "price": st.one_of(
                        st.floats(
                            min_value=0.01,
                            max_value=1e6,
                            allow_nan=False,
                            allow_infinity=False,
                        ),
                        st.just("invalid"),
                        st.just(""),
                    ),
                    "volume": st.one_of(
                        st.floats(
                            min_value=0.0,
                            max_value=1e9,
                            allow_nan=False,
                            allow_infinity=False,
                        ),
                        st.just("invalid"),
                        st.just(""),
                        st.just(None),
                    ),
                }
            ),
            min_size=0,
            max_size=50,
        )
    )
    def test_csv_handles_malformed_data_gracefully(
        self, rows: list[dict], tmp_path: Path
    ) -> None:
        """CSV parser should handle malformed data without crashing."""
        csv_path = tmp_path / "fuzz.csv"

        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["ts", "price", "volume"])
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

        ingestor = DataIngestor()
        records: list[Ticker] = []

        # Should not crash, even with malformed data
        ingestor.historical_csv(str(csv_path), records.append)

        # All successfully parsed records should have valid numeric values
        for record in records:
            assert isinstance(record.ts, float)
            assert isinstance(record.price, Decimal)
            assert isinstance(record.volume, Decimal)
            assert math.isfinite(record.ts)
            assert math.isfinite(float(record.price))
            assert math.isfinite(float(record.volume))

    def test_csv_rejects_missing_header(self, tmp_path: Path) -> None:
        """CSV without proper header should raise ValueError."""
        csv_path = tmp_path / "no_header.csv"
        with csv_path.open("w", encoding="utf-8") as f:
            # Write raw data without header - will be interpreted as header
            f.write("1,100.0,5.0\n")
            f.write("2,101.0,6.0\n")

        ingestor = DataIngestor()
        # The first row becomes the "header", so required fields won't be found
        with pytest.raises(ValueError, match="missing required columns"):
            ingestor.historical_csv(str(csv_path), lambda _: None)

    def test_csv_rejects_missing_required_columns(self, tmp_path: Path) -> None:
        """CSV missing required columns should raise ValueError."""
        csv_path = tmp_path / "missing_cols.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["timestamp", "value"])
            writer.writeheader()
            writer.writerow({"timestamp": "1", "value": "100"})

        ingestor = DataIngestor()
        with pytest.raises(ValueError, match="missing required columns"):
            ingestor.historical_csv(str(csv_path), lambda _: None)

    def test_csv_with_only_headers(self, tmp_path: Path) -> None:
        """CSV with only headers and no data rows should work."""
        csv_path = tmp_path / "only_headers.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["ts", "price", "volume"])
            writer.writeheader()

        ingestor = DataIngestor()
        records: list[Ticker] = []
        ingestor.historical_csv(str(csv_path), records.append)
        assert len(records) == 0

    @settings(
        max_examples=50,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        ts=st.floats(min_value=0.0, max_value=2e9),
        price=st.floats(min_value=0.001, max_value=1e8),
        volume=st.floats(min_value=0.0, max_value=1e10),
    )
    def test_csv_parses_valid_floats_correctly(
        self, ts: float, price: float, volume: float, tmp_path: Path
    ) -> None:
        """CSV should correctly parse valid float values."""
        csv_path = tmp_path / "valid.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["ts", "price", "volume"])
            writer.writeheader()
            writer.writerow({"ts": str(ts), "price": str(price), "volume": str(volume)})

        ingestor = DataIngestor()
        records: list[Ticker] = []
        ingestor.historical_csv(str(csv_path), records.append)

        assert len(records) == 1
        assert records[0].ts == pytest.approx(ts, rel=FLOAT_REL_TOL, abs=FLOAT_ABS_TOL)
        assert float(records[0].price) == pytest.approx(
            price, rel=FLOAT_REL_TOL, abs=FLOAT_ABS_TOL
        )
        assert float(records[0].volume) == pytest.approx(
            volume, rel=FLOAT_REL_TOL, abs=FLOAT_ABS_TOL
        )

    def test_csv_handles_missing_volume_as_zero(self, tmp_path: Path) -> None:
        """CSV with missing volume field should default to 0."""
        csv_path = tmp_path / "no_volume.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["ts", "price"])
            writer.writeheader()
            writer.writerow({"ts": "1", "price": "100"})

        ingestor = DataIngestor()
        records: list[Ticker] = []
        ingestor.historical_csv(str(csv_path), records.append)

        assert len(records) == 1
        assert records[0].volume == Decimal("0")

    def test_csv_handles_empty_volume_as_zero(self, tmp_path: Path) -> None:
        """CSV with empty volume field should default to 0."""
        csv_path = tmp_path / "empty_volume.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["ts", "price", "volume"])
            writer.writeheader()
            writer.writerow({"ts": "1", "price": "100", "volume": ""})

        ingestor = DataIngestor()
        records: list[Ticker] = []
        ingestor.historical_csv(str(csv_path), records.append)

        assert len(records) == 1
        assert records[0].volume == Decimal("0")

    @settings(
        max_examples=50,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        valid_rows=st.integers(min_value=1, max_value=20),
        invalid_rows=st.integers(min_value=1, max_value=20),
    )
    def test_csv_skips_invalid_rows_and_continues(
        self, valid_rows: int, invalid_rows: int, tmp_path: Path
    ) -> None:
        """CSV parser should skip invalid rows and continue processing."""
        csv_path = tmp_path / "mixed.csv"

        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["ts", "price", "volume"])
            writer.writeheader()

            # Write valid rows
            for i in range(valid_rows):
                writer.writerow(
                    {"ts": str(i), "price": str(100 + i), "volume": str(10 * i)}
                )

            # Write invalid rows
            for i in range(invalid_rows):
                writer.writerow({"ts": "bad", "price": "data", "volume": "here"})

        ingestor = DataIngestor()
        records: list[Ticker] = []
        ingestor.historical_csv(str(csv_path), records.append)

        # Should have parsed exactly the valid rows
        assert len(records) == valid_rows

    def test_csv_with_extra_columns_is_accepted(self, tmp_path: Path) -> None:
        """CSV with extra columns beyond required should work."""
        csv_path = tmp_path / "extra_cols.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f, fieldnames=["ts", "price", "volume", "open", "high", "low"]
            )
            writer.writeheader()
            writer.writerow(
                {
                    "ts": "1",
                    "price": "100",
                    "volume": "5",
                    "open": "99",
                    "high": "101",
                    "low": "98",
                }
            )

        ingestor = DataIngestor()
        records: list[Ticker] = []
        ingestor.historical_csv(str(csv_path), records.append)

        assert len(records) == 1
        assert records[0].ts == 1.0
        assert float(records[0].price) == pytest.approx(100.0)

    def test_csv_with_unicode_in_data(self, tmp_path: Path) -> None:
        """CSV with unicode characters should be handled."""
        csv_path = tmp_path / "unicode.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["ts", "price", "volume", "symbol"])
            writer.writeheader()
            writer.writerow(
                {"ts": "1", "price": "100", "volume": "5", "symbol": "₿TC/USDT"}
            )

        ingestor = DataIngestor()
        records: list[Ticker] = []
        ingestor.historical_csv(str(csv_path), records.append)

        assert len(records) == 1


class TestTickerProperties:
    """Property-based tests for the Ticker model."""

    @settings(max_examples=100, deadline=None)
    @given(
        ts=st.floats(
            min_value=0.0, max_value=2e9, allow_nan=False, allow_infinity=False
        ),
        price=st.floats(
            min_value=0.01, max_value=1e8, allow_nan=False, allow_infinity=False
        ),
        volume=st.floats(
            min_value=0.0, max_value=1e10, allow_nan=False, allow_infinity=False
        ),
    )
    def test_ticker_creation(self, ts: float, price: float, volume: float) -> None:
        """Ticker should be created with provided values."""
        ticker = Ticker.create(
            symbol="FUZZ", venue="TEST", price=price, timestamp=ts, volume=volume
        )
        # ``Ticker`` normalises the provided timestamp to a timezone-aware
        # ``datetime`` under the hood.  Python datetimes carry microsecond
        # precision, so converting back to epoch seconds can incur a small
        # absolute rounding error for very small floats.  An explicit absolute
        # tolerance keeps the property-based test robust without masking
        # genuine large deviations.
        assert ticker.ts == pytest.approx(ts, abs=1e-6)
        assert float(ticker.price) == pytest.approx(price)
        assert float(ticker.volume) == pytest.approx(volume)

    def test_ticker_volume_defaults_to_zero(self) -> None:
        """Ticker volume should default to 0.0 if not provided."""
        ticker = Ticker.create(
            symbol="FUZZ", venue="TEST", price=100.0, timestamp=1234.5
        )
        assert ticker.volume == Decimal("0")
