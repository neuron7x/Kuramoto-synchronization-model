# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for synthetic market feed generator."""


from core.data.market_feed import validate_recording
from core.data.market_feed_generator import SyntheticMarketFeedGenerator


class TestSyntheticMarketFeedGenerator:
    """Tests for synthetic market feed generation."""

    def test_generate_stable_regime(self):
        """Test generating stable market regime."""
        generator = SyntheticMarketFeedGenerator(seed=42)
        recording = generator.generate(num_records=100, regime="stable")

        assert len(recording) == 100
        assert recording.metadata is not None
        assert recording.metadata.symbol == "BTCUSD"
        assert recording.metadata.venue == "synthetic"

        # Validate quality
        result = validate_recording(recording)
        assert result["valid"] is True

    def test_generate_trending_up(self):
        """Test generating uptrend."""
        generator = SyntheticMarketFeedGenerator(seed=42)
        recording = generator.generate(num_records=100, regime="trending_up")

        # Check that price generally increases
        start_price = float(recording[0].last)
        end_price = float(recording[-1].last)

        # Should trend upward (allowing for some volatility)
        assert end_price > start_price * 0.99  # At least not down much

    def test_generate_trending_down(self):
        """Test generating downtrend."""
        generator = SyntheticMarketFeedGenerator(seed=42)
        recording = generator.generate(num_records=100, regime="trending_down")

        # Check that price generally decreases
        start_price = float(recording[0].last)
        end_price = float(recording[-1].last)

        # Should trend downward (allowing for some volatility)
        assert end_price < start_price * 1.01  # At least not up much

    def test_generate_volatile_regime(self):
        """Test generating volatile market."""
        generator = SyntheticMarketFeedGenerator(seed=42)
        recording = generator.generate(num_records=100, regime="volatile")

        # Calculate price changes
        prices = [float(r.last) for r in recording.records]
        price_changes = [
            abs(prices[i] - prices[i - 1]) / prices[i - 1]
            for i in range(1, len(prices))
        ]

        avg_change = sum(price_changes) / len(price_changes)

        # Volatile regime should have larger price changes
        assert avg_change > 0.0001  # At least some movement

    def test_reproducibility(self):
        """Test that same seed produces same results."""
        generator1 = SyntheticMarketFeedGenerator(seed=42)
        recording1 = generator1.generate(num_records=50, regime="stable")

        generator2 = SyntheticMarketFeedGenerator(seed=42)
        recording2 = generator2.generate(num_records=50, regime="stable")

        # Should be identical
        for r1, r2 in zip(recording1.records, recording2.records):
            assert r1.exchange_ts == r2.exchange_ts
            assert r1.bid == r2.bid
            assert r1.ask == r2.ask
            assert r1.last == r2.last
            assert r1.volume == r2.volume

    def test_different_seeds_produce_different_results(self):
        """Test that different seeds produce different results."""
        generator1 = SyntheticMarketFeedGenerator(seed=42)
        recording1 = generator1.generate(num_records=50, regime="stable")

        generator2 = SyntheticMarketFeedGenerator(seed=123)
        recording2 = generator2.generate(num_records=50, regime="stable")

        # Should be different (at least some records)
        differences = sum(
            1
            for r1, r2 in zip(recording1.records, recording2.records)
            if r1.last != r2.last
        )
        assert differences > 0

    def test_flash_crash(self):
        """Test flash crash generation."""
        generator = SyntheticMarketFeedGenerator(seed=42)
        recording = generator.generate_flash_crash(
            num_records=100,
            crash_position=0.5,
            crash_magnitude=0.05,  # 5% crash
        )

        assert len(recording) == 100

        # Find the crash point
        prices = [float(r.last) for r in recording.records]
        crash_idx = 50  # Middle

        # Check crash happened
        before_crash = prices[crash_idx - 5 : crash_idx]
        at_crash = prices[crash_idx : crash_idx + 3]

        avg_before = sum(before_crash) / len(before_crash)
        min_at_crash = min(at_crash)

        # Price should drop significantly
        assert min_at_crash < avg_before * 0.96  # At least 4% drop

    def test_flash_crash_recovery(self):
        """Test that flash crash includes recovery."""
        generator = SyntheticMarketFeedGenerator(seed=42)
        recording = generator.generate_flash_crash(
            num_records=100,
            crash_position=0.3,
            crash_magnitude=0.05,
            recovery_speed=0.8,
        )

        prices = [float(r.last) for r in recording.records]
        crash_idx = 30

        # Check recovery
        before_crash = prices[crash_idx - 5 : crash_idx]
        after_recovery = prices[-5:]

        avg_before = sum(before_crash) / len(before_crash)
        avg_after = sum(after_recovery) / len(after_recovery)

        # Should recover somewhat (may not be full recovery)
        assert avg_after > avg_before * 0.90

    def test_regime_transition(self):
        """Test regime transition generation."""
        generator = SyntheticMarketFeedGenerator(seed=42)
        recording = generator.generate_regime_transition(
            num_records=90,
            regimes=["stable", "trending_up", "volatile"],
            transition_points=[0.33, 0.67],
        )

        assert len(recording) == 90
        assert recording.metadata is not None
        assert "regime_transition" in recording.metadata.tags

        # Validate quality
        result = validate_recording(recording)
        assert result["valid"] is True

    def test_latency_distribution(self):
        """Test that latency follows expected distribution."""
        generator = SyntheticMarketFeedGenerator(
            seed=42,
            latency_mean_ms=50.0,
            latency_std_ms=10.0,
        )
        recording = generator.generate(num_records=100, regime="stable")

        latencies = [r.latency_ms for r in recording.records]
        avg_latency = sum(latencies) / len(latencies)

        # Should be close to mean (within 20%)
        assert 40.0 < avg_latency < 60.0

    def test_spread_reasonable(self):
        """Test that spreads are reasonable."""
        generator = SyntheticMarketFeedGenerator(
            seed=42,
            base_price=50000.0,
            base_spread_bps=5.0,
        )
        recording = generator.generate(num_records=100, regime="stable")

        spreads = [float(r.spread) for r in recording.records]

        # All spreads should be positive
        assert all(s > 0 for s in spreads)

        # Should be in reasonable range (within order of magnitude)
        expected_spread = 50000 * 0.0005  # 5 bps
        avg_spread = sum(spreads) / len(spreads)
        assert expected_spread * 0.5 < avg_spread < expected_spread * 3.0

    def test_volume_positive(self):
        """Test that all volumes are non-negative."""
        generator = SyntheticMarketFeedGenerator(seed=42)
        recording = generator.generate(num_records=100, regime="stable")

        volumes = [float(r.volume) for r in recording.records]
        assert all(v >= 0 for v in volumes)

    def test_metadata_populated(self):
        """Test that metadata is properly populated."""
        generator = SyntheticMarketFeedGenerator(seed=42)
        recording = generator.generate(num_records=50, regime="trending_up")

        assert recording.metadata is not None
        assert recording.metadata.record_count == 50
        assert recording.metadata.symbol == "BTCUSD"
        assert recording.metadata.venue == "synthetic"
        assert recording.metadata.version == "1.0.0"
        assert "trending_up" in recording.metadata.description
        assert "synthetic" in recording.metadata.tags
        assert "trending_up" in recording.metadata.tags

    def test_custom_parameters(self):
        """Test custom generator parameters."""
        generator = SyntheticMarketFeedGenerator(
            seed=42,
            base_price=100000.0,
            base_spread_bps=10.0,
            tick_interval_ms=200.0,
        )
        recording = generator.generate(num_records=10, regime="stable")

        # Check that base price is respected
        prices = [float(r.last) for r in recording.records]
        avg_price = sum(prices) / len(prices)
        assert 90000 < avg_price < 110000  # Within 10% of base
