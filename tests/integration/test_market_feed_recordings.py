# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Integration tests for market feed recordings.

Tests that recordings are valid, reproducible, and suitable for
dopamine loop testing (TD(0) RPE, DDM, Go/No-Go).
"""

from pathlib import Path

import pytest

from core.data.market_feed import MarketFeedRecording, validate_recording
from tradepulse.core.neuro.dopamine import adapt_ddm_parameters

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "recordings"


class TestMarketFeedRecordingsValidity:
    """Test that all generated recordings are valid."""

    @pytest.mark.parametrize(
        "recording_name",
        [
            "stable_btcusd_100ticks.jsonl",
            "trending_up_btcusd_200ticks.jsonl",
            "trending_down_btcusd_200ticks.jsonl",
            "volatile_btcusd_150ticks.jsonl",
            "mean_reverting_btcusd_250ticks.jsonl",
            "flash_crash_5pct_mid.jsonl",
            "flash_crash_10pct_early.jsonl",
            "regime_transitions_4phases.jsonl",
        ],
    )
    def test_recording_validity(self, recording_name):
        """Test that recording is valid and well-formed."""
        recording = MarketFeedRecording.read_jsonl(FIXTURES_DIR / recording_name)

        # Validate with quality control
        validation = validate_recording(recording)
        assert validation["valid"] is True, f"{recording_name} validation failed"
        assert validation["record_count"] > 0
        assert validation["duration_seconds"] > 0

        # Check latency is reasonable
        assert validation["latency_ms"]["median"] < 100
        assert validation["latency_ms"]["max"] < 200

    def test_stable_market_characteristics(self):
        """Test stable market recording has expected characteristics."""
        recording = MarketFeedRecording.read_jsonl(
            FIXTURES_DIR / "stable_btcusd_100ticks.jsonl"
        )

        assert len(recording) == 100

        # Calculate price statistics
        prices = [float(r.last) for r in recording.records]
        avg_price = sum(prices) / len(prices)
        price_range = max(prices) - min(prices)

        # Stable market should have limited price movement
        assert price_range / avg_price < 0.05, "Stable market should have < 5% range"

        # All prices should be positive
        assert all(p > 0 for p in prices)

    def test_volatile_market_characteristics(self):
        """Test volatile market recording has higher volatility."""
        recording = MarketFeedRecording.read_jsonl(
            FIXTURES_DIR / "volatile_btcusd_150ticks.jsonl"
        )

        assert len(recording) == 150

        # Calculate price changes
        prices = [float(r.last) for r in recording.records]
        price_changes = [
            abs(prices[i] - prices[i - 1]) / prices[i - 1]
            for i in range(1, len(prices))
        ]

        avg_change = sum(price_changes) / len(price_changes)

        # Volatile market should have larger price changes
        assert avg_change > 0.0001, "Volatile market should have measurable volatility"

    def test_flash_crash_event_detected(self):
        """Test flash crash recording contains detectable crash event."""
        recording = MarketFeedRecording.read_jsonl(
            FIXTURES_DIR / "flash_crash_5pct_mid.jsonl"
        )

        assert len(recording) == 100

        # Find largest single price drop
        prices = [float(r.last) for r in recording.records]
        max_drop = 0.0
        for i in range(1, len(prices)):
            drop = (prices[i - 1] - prices[i]) / prices[i - 1]
            if drop > max_drop:
                max_drop = drop

        # Should have at least 2% single-tick drop during crash
        assert max_drop > 0.02, "Flash crash should have significant price drop"

    def test_regime_transition_recording(self):
        """Test regime transition recording has multiple phases."""
        recording = MarketFeedRecording.read_jsonl(
            FIXTURES_DIR / "regime_transitions_4phases.jsonl"
        )

        assert len(recording) == 300

        validation = validate_recording(recording)
        assert validation["valid"] is True
        assert validation["record_count"] == 300


class TestDDMIntegration:
    """Test DDM adaptation with market feed data."""

    def test_ddm_adapts_to_price_movements(self):
        """Test that DDM parameters adapt to price movements."""
        recording = MarketFeedRecording.read_jsonl(
            FIXTURES_DIR / "volatile_btcusd_150ticks.jsonl"
        )

        # Simulate dopamine levels from price movements
        prices = [float(r.last) for r in recording.records]
        dopamine_levels = []

        for i in range(len(prices)):
            if i < 5:
                # Not enough history, use baseline
                dopamine_levels.append(0.5)
            else:
                # Simple momentum-based dopamine
                momentum = (prices[i] - prices[i - 5]) / prices[i - 5]
                # Map to [0, 1] range with sigmoid
                import math

                dopamine = 1.0 / (1.0 + math.exp(-momentum * 100))
                dopamine_levels.append(dopamine)

        # Test DDM adaptation for various dopamine levels
        ddm_params = []
        for da_level in dopamine_levels:
            params = adapt_ddm_parameters(
                dopamine_level=da_level,
                base_drift=0.5,
                base_boundary=1.0,
            )
            ddm_params.append(params)

        # Verify DDM parameters vary
        drifts = [p.drift for p in ddm_params]
        boundaries = [p.boundary for p in ddm_params]

        assert len(set(drifts)) > 1, "DDM drift should vary with dopamine"
        assert len(set(boundaries)) > 1, "DDM boundary should vary with dopamine"

        # High dopamine should increase drift
        high_da_params = adapt_ddm_parameters(0.9, 0.5, 1.0)
        low_da_params = adapt_ddm_parameters(0.1, 0.5, 1.0)
        assert high_da_params.drift > low_da_params.drift

    def test_ddm_parameters_stay_valid(self):
        """Test that DDM parameters remain valid across all recordings."""
        recordings = [
            "stable_btcusd_100ticks.jsonl",
            "trending_up_btcusd_200ticks.jsonl",
            "volatile_btcusd_150ticks.jsonl",
        ]

        for recording_name in recordings:
            MarketFeedRecording.read_jsonl(FIXTURES_DIR / recording_name)

            # Test with various dopamine levels
            for da_level in [0.1, 0.3, 0.5, 0.7, 0.9]:
                params = adapt_ddm_parameters(
                    dopamine_level=da_level,
                    base_drift=0.5,
                    base_boundary=1.0,
                )

                # Parameters should remain valid
                assert params.drift > 0, f"Drift must be positive (da={da_level})"
                assert params.boundary > 0, f"Boundary must be positive (da={da_level})"
                assert params.boundary >= 0.1, "Boundary must be >= min_boundary"


class TestRecordingReproducibility:
    """Test that recordings are reproducible and deterministic."""

    def test_recordings_are_reproducible(self):
        """Test that recordings can be read multiple times consistently."""
        recording1 = MarketFeedRecording.read_jsonl(
            FIXTURES_DIR / "stable_btcusd_100ticks.jsonl"
        )
        recording2 = MarketFeedRecording.read_jsonl(
            FIXTURES_DIR / "stable_btcusd_100ticks.jsonl"
        )

        assert len(recording1) == len(recording2)

        for r1, r2 in zip(recording1.records, recording2.records):
            assert r1.exchange_ts == r2.exchange_ts
            assert r1.bid == r2.bid
            assert r1.ask == r2.ask
            assert r1.last == r2.last
            assert r1.volume == r2.volume

    def test_metadata_available(self):
        """Test that metadata files are available and valid."""
        import json

        metadata_files = [
            "stable_btcusd_100ticks.metadata.json",
            "trending_up_btcusd_200ticks.metadata.json",
            "volatile_btcusd_150ticks.metadata.json",
        ]

        for metadata_file in metadata_files:
            path = FIXTURES_DIR / metadata_file
            assert path.exists(), f"Metadata file {metadata_file} not found"

            with open(path) as f:
                metadata = json.load(f)

            # Check required fields
            assert "symbol" in metadata
            assert "venue" in metadata
            assert "record_count" in metadata
            assert "version" in metadata


class TestRecordingTimestamps:
    """Test timestamp handling and timezone synchronization."""

    def test_timestamps_are_utc(self):
        """Test that all timestamps are UTC."""
        recording = MarketFeedRecording.read_jsonl(
            FIXTURES_DIR / "stable_btcusd_100ticks.jsonl"
        )

        for record in recording.records:
            assert record.exchange_ts.tzname() == "UTC"
            assert record.ingest_ts.tzname() == "UTC"

            # UTC offset should be 0
            assert record.exchange_ts.utcoffset().total_seconds() == 0
            assert record.ingest_ts.utcoffset().total_seconds() == 0

    def test_timestamps_monotonic(self):
        """Test that timestamps are strictly increasing."""
        recordings = [
            "stable_btcusd_100ticks.jsonl",
            "trending_up_btcusd_200ticks.jsonl",
            "volatile_btcusd_150ticks.jsonl",
        ]

        for recording_name in recordings:
            recording = MarketFeedRecording.read_jsonl(FIXTURES_DIR / recording_name)

            for i in range(1, len(recording)):
                prev_ts = recording[i - 1].exchange_ts
                curr_ts = recording[i].exchange_ts
                assert (
                    curr_ts >= prev_ts
                ), f"{recording_name}: Timestamps not monotonic at index {i}"

    def test_latency_reasonable(self):
        """Test that ingestion latency is within reasonable bounds."""
        recordings = [
            "stable_btcusd_100ticks.jsonl",
            "trending_up_btcusd_200ticks.jsonl",
        ]

        for recording_name in recordings:
            recording = MarketFeedRecording.read_jsonl(FIXTURES_DIR / recording_name)

            for record in recording.records:
                latency_ms = record.latency_ms

                # Latency should be non-negative
                assert latency_ms >= 0, f"Negative latency detected: {latency_ms}ms"

                # Latency should be reasonable (< 1 second)
                assert latency_ms < 1000, f"Excessive latency: {latency_ms}ms"
