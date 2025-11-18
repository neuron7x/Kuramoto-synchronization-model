# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for market feed recording infrastructure."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from core.data.market_feed import (
    MarketFeedMetadata,
    MarketFeedRecord,
    MarketFeedRecording,
    validate_recording,
)


class TestMarketFeedRecord:
    """Tests for MarketFeedRecord schema validation."""

    def test_valid_record_creation(self):
        """Test creating a valid market feed record."""
        exchange_ts = datetime.now(timezone.utc)
        ingest_ts = exchange_ts + timedelta(milliseconds=50)

        record = MarketFeedRecord(
            exchange_ts=exchange_ts,
            ingest_ts=ingest_ts,
            bid=Decimal("50000.00"),
            ask=Decimal("50000.50"),
            last=Decimal("50000.25"),
            volume=Decimal("1.5"),
        )

        assert record.exchange_ts == exchange_ts
        assert record.ingest_ts == ingest_ts
        assert record.bid == Decimal("50000.00")
        assert record.ask == Decimal("50000.50")
        assert record.last == Decimal("50000.25")
        assert record.volume == Decimal("1.5")

    def test_timestamp_parsing_from_iso_string(self):
        """Test parsing timestamps from ISO 8601 strings."""
        record = MarketFeedRecord(
            exchange_ts="2024-03-05T14:30:00.123456Z",
            ingest_ts="2024-03-05T14:30:00.168923Z",
            bid=Decimal("50000.00"),
            ask=Decimal("50000.50"),
            last=Decimal("50000.25"),
            volume=Decimal("1.5"),
        )

        assert record.exchange_ts.tzinfo == timezone.utc
        assert record.ingest_ts.tzinfo == timezone.utc
        assert record.exchange_ts < record.ingest_ts

    def test_numeric_coercion(self):
        """Test automatic coercion of numeric types."""
        record = MarketFeedRecord(
            exchange_ts="2024-03-05T14:30:00Z",
            ingest_ts="2024-03-05T14:30:00.050Z",
            bid=50000.00,  # float
            ask="50000.50",  # string
            last=50000,  # int
            volume=1.5,
        )

        assert isinstance(record.bid, Decimal)
        assert isinstance(record.ask, Decimal)
        assert isinstance(record.last, Decimal)
        assert isinstance(record.volume, Decimal)

    def test_bid_must_be_less_than_or_equal_to_ask(self):
        """Test that bid <= ask is enforced."""
        with pytest.raises(ValueError, match="Bid .* must be <= Ask"):
            MarketFeedRecord(
                exchange_ts="2024-03-05T14:30:00Z",
                ingest_ts="2024-03-05T14:30:00.050Z",
                bid=Decimal("50001.00"),  # Bid > Ask
                ask=Decimal("50000.00"),
                last=Decimal("50000.50"),
                volume=Decimal("1.0"),
            )

    def test_last_price_within_reasonable_range(self):
        """Test that last price is within reasonable range of bid-ask."""
        # Should pass - last is within spread
        record = MarketFeedRecord(
            exchange_ts="2024-03-05T14:30:00Z",
            ingest_ts="2024-03-05T14:30:00.050Z",
            bid=Decimal("50000.00"),
            ask=Decimal("50001.00"),
            last=Decimal("50000.50"),
            volume=Decimal("1.0"),
        )
        assert record.last == Decimal("50000.50")

        # Should fail - last is far outside spread
        with pytest.raises(ValueError, match="Last price .* outside reasonable range"):
            MarketFeedRecord(
                exchange_ts="2024-03-05T14:30:00Z",
                ingest_ts="2024-03-05T14:30:00.050Z",
                bid=Decimal("50000.00"),
                ask=Decimal("50001.00"),
                last=Decimal("60000.00"),  # Way too high
                volume=Decimal("1.0"),
            )

    def test_latency_validation(self):
        """Test that excessive latency is rejected."""
        exchange_ts = datetime.now(timezone.utc)

        # Should pass - reasonable latency
        record = MarketFeedRecord(
            exchange_ts=exchange_ts,
            ingest_ts=exchange_ts + timedelta(milliseconds=50),
            bid=Decimal("50000.00"),
            ask=Decimal("50000.50"),
            last=Decimal("50000.25"),
            volume=Decimal("1.0"),
        )
        assert record.latency_ms == pytest.approx(50.0, abs=1.0)

        # Should fail - excessive latency
        with pytest.raises(ValueError, match="Latency .* exceeds maximum threshold"):
            MarketFeedRecord(
                exchange_ts=exchange_ts,
                ingest_ts=exchange_ts + timedelta(seconds=20),  # 20 seconds
                bid=Decimal("50000.00"),
                ask=Decimal("50000.50"),
                last=Decimal("50000.25"),
                volume=Decimal("1.0"),
            )

    def test_negative_prices_rejected(self):
        """Test that negative prices are rejected."""
        exchange_ts = datetime.now(timezone.utc)

        with pytest.raises(ValueError):
            MarketFeedRecord(
                exchange_ts=exchange_ts,
                ingest_ts=exchange_ts + timedelta(milliseconds=50),
                bid=Decimal("-50000.00"),
                ask=Decimal("50000.50"),
                last=Decimal("50000.25"),
                volume=Decimal("1.0"),
            )

    def test_negative_volume_rejected(self):
        """Test that negative volume is rejected."""
        exchange_ts = datetime.now(timezone.utc)

        with pytest.raises(ValueError):
            MarketFeedRecord(
                exchange_ts=exchange_ts,
                ingest_ts=exchange_ts + timedelta(milliseconds=50),
                bid=Decimal("50000.00"),
                ask=Decimal("50000.50"),
                last=Decimal("50000.25"),
                volume=Decimal("-1.0"),
            )

    def test_jsonl_serialization_roundtrip(self):
        """Test JSONL serialization and deserialization."""
        exchange_ts = datetime(2024, 3, 5, 14, 30, 0, 123456, tzinfo=timezone.utc)
        ingest_ts = datetime(2024, 3, 5, 14, 30, 0, 168923, tzinfo=timezone.utc)

        original = MarketFeedRecord(
            exchange_ts=exchange_ts,
            ingest_ts=ingest_ts,
            bid=Decimal("50000.12"),
            ask=Decimal("50000.54"),
            last=Decimal("50000.33"),
            volume=Decimal("0.18"),
        )

        jsonl = original.to_jsonl()
        restored = MarketFeedRecord.from_jsonl(jsonl)

        assert restored.exchange_ts == original.exchange_ts
        assert restored.ingest_ts == original.ingest_ts
        assert restored.bid == original.bid
        assert restored.ask == original.ask
        assert restored.last == original.last
        assert restored.volume == original.volume

    def test_properties(self):
        """Test computed properties."""
        record = MarketFeedRecord(
            exchange_ts="2024-03-05T14:30:00.000000Z",
            ingest_ts="2024-03-05T14:30:00.045000Z",
            bid=Decimal("50000.00"),
            ask=Decimal("50001.00"),
            last=Decimal("50000.50"),
            volume=Decimal("1.0"),
        )

        assert record.latency_ms == pytest.approx(45.0, abs=1.0)
        assert record.spread == Decimal("1.00")
        assert record.mid_price == Decimal("50000.50")


class TestMarketFeedRecording:
    """Tests for MarketFeedRecording container."""

    def test_create_empty_recording(self):
        """Test creating an empty recording."""
        recording = MarketFeedRecording([])
        assert len(recording) == 0

    def test_monotonicity_validation(self):
        """Test that non-monotonic timestamps are rejected."""
        exchange_ts = datetime.now(timezone.utc)

        records = [
            MarketFeedRecord(
                exchange_ts=exchange_ts,
                ingest_ts=exchange_ts + timedelta(milliseconds=50),
                bid=Decimal("50000.00"),
                ask=Decimal("50000.50"),
                last=Decimal("50000.25"),
                volume=Decimal("1.0"),
            ),
            MarketFeedRecord(
                exchange_ts=exchange_ts - timedelta(seconds=1),  # Goes backward!
                ingest_ts=exchange_ts + timedelta(milliseconds=100),
                bid=Decimal("50001.00"),
                ask=Decimal("50001.50"),
                last=Decimal("50001.25"),
                volume=Decimal("1.0"),
            ),
        ]

        with pytest.raises(ValueError, match="not monotonic"):
            MarketFeedRecording(records)

    def test_file_io_roundtrip(self, tmp_path):
        """Test writing and reading from file."""
        exchange_ts = datetime.now(timezone.utc)

        records = [
            MarketFeedRecord(
                exchange_ts=exchange_ts + timedelta(seconds=i),
                ingest_ts=exchange_ts + timedelta(seconds=i, milliseconds=50),
                bid=Decimal(f"{50000 + i}.00"),
                ask=Decimal(f"{50000 + i}.50"),
                last=Decimal(f"{50000 + i}.25"),
                volume=Decimal("1.0"),
            )
            for i in range(10)
        ]

        recording = MarketFeedRecording(records)

        filepath = tmp_path / "test_recording.jsonl"
        recording.write_jsonl(filepath)

        assert filepath.exists()

        restored = MarketFeedRecording.read_jsonl(filepath)
        assert len(restored) == len(recording)

        for original, restored_record in zip(recording.records, restored.records):
            assert restored_record.exchange_ts == original.exchange_ts
            assert restored_record.bid == original.bid

    def test_metadata_io(self, tmp_path):
        """Test writing and reading with metadata."""
        exchange_ts = datetime.now(timezone.utc)

        records = [
            MarketFeedRecord(
                exchange_ts=exchange_ts + timedelta(seconds=i),
                ingest_ts=exchange_ts + timedelta(seconds=i, milliseconds=50),
                bid=Decimal(f"{50000 + i}.00"),
                ask=Decimal(f"{50000 + i}.50"),
                last=Decimal(f"{50000 + i}.25"),
                volume=Decimal("1.0"),
            )
            for i in range(5)
        ]

        metadata = MarketFeedMetadata(
            symbol="BTCUSD",
            venue="binance",
            start_time=records[0].exchange_ts,
            end_time=records[-1].exchange_ts,
            record_count=len(records),
            description="Test recording",
            tags=["test", "synthetic"],
        )

        recording = MarketFeedRecording(records, metadata)

        jsonl_path = tmp_path / "recording.jsonl"
        metadata_path = tmp_path / "recording.metadata.json"

        recording.write_with_metadata(jsonl_path, metadata_path)

        assert jsonl_path.exists()
        assert metadata_path.exists()

        restored = MarketFeedRecording.read_with_metadata(jsonl_path, metadata_path)

        assert len(restored) == len(recording)
        assert restored.metadata is not None
        assert restored.metadata.symbol == metadata.symbol
        assert restored.metadata.venue == metadata.venue
        assert restored.metadata.record_count == metadata.record_count


class TestRecordingValidation:
    """Tests for recording quality validation."""

    def test_validate_empty_recording(self):
        """Test validation of empty recording."""
        recording = MarketFeedRecording([])
        result = validate_recording(recording)

        assert result["valid"] is False
        assert "Empty" in result["error"]

    def test_validate_good_recording(self):
        """Test validation of high-quality recording."""
        exchange_ts = datetime.now(timezone.utc)

        records = [
            MarketFeedRecord(
                exchange_ts=exchange_ts + timedelta(milliseconds=i * 100),
                ingest_ts=exchange_ts + timedelta(milliseconds=i * 100 + 45),
                bid=Decimal(f"{50000 + i * 0.1:.2f}"),
                ask=Decimal(f"{50000 + i * 0.1 + 0.5:.2f}"),
                last=Decimal(f"{50000 + i * 0.1 + 0.25:.2f}"),
                volume=Decimal("1.0"),
            )
            for i in range(100)
        ]

        recording = MarketFeedRecording(records)
        result = validate_recording(recording)

        assert result["valid"] is True
        assert result["record_count"] == 100
        assert result["latency_ms"]["median"] < 100
        assert len(result["warnings"]) == 0

    def test_validate_high_latency_warning(self):
        """Test that high latency generates warning."""
        exchange_ts = datetime.now(timezone.utc)

        records = [
            MarketFeedRecord(
                exchange_ts=exchange_ts + timedelta(seconds=i),
                ingest_ts=exchange_ts + timedelta(seconds=i, milliseconds=150),
                bid=Decimal("50000.00"),
                ask=Decimal("50000.50"),
                last=Decimal("50000.25"),
                volume=Decimal("1.0"),
            )
            for i in range(10)
        ]

        recording = MarketFeedRecording(records)
        result = validate_recording(recording)

        assert result["valid"] is True
        assert any("latency" in w.lower() for w in result["warnings"])

    def test_validate_time_gap_warning(self):
        """Test that large time gaps generate warning."""
        exchange_ts = datetime.now(timezone.utc)

        records = [
            MarketFeedRecord(
                exchange_ts=exchange_ts + timedelta(seconds=i * 10),  # 10 second gaps
                ingest_ts=exchange_ts + timedelta(seconds=i * 10, milliseconds=50),
                bid=Decimal("50000.00"),
                ask=Decimal("50000.50"),
                last=Decimal("50000.25"),
                volume=Decimal("1.0"),
            )
            for i in range(10)
        ]

        recording = MarketFeedRecording(records)
        result = validate_recording(recording)

        assert result["valid"] is True
        assert any("gap" in w.lower() for w in result["warnings"])
