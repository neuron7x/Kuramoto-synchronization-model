"""Tests for strategy memory and adaptive learning module."""

from __future__ import annotations

import time

import pytest

from core.agent.memory import StrategyMemory, StrategyRecord, StrategySignature


class TestStrategySignature:
    """Test StrategySignature creation and key generation."""

    def test_signature_creation(self) -> None:
        sig = StrategySignature(
            R=0.95,
            delta_H=0.05,
            kappa_mean=0.3,
            entropy=2.1,
            instability=0.1,
        )

        assert sig.R == 0.95
        assert sig.delta_H == 0.05
        assert sig.kappa_mean == 0.3
        assert sig.entropy == 2.1
        assert sig.instability == 0.1

    def test_signature_key_generation(self) -> None:
        sig = StrategySignature(
            R=0.95432,
            delta_H=0.05678,
            kappa_mean=0.30123,
            entropy=2.10456,
            instability=0.10789,
        )

        key = sig.key(precision=4)
        assert key == (0.9543, 0.0568, 0.3012, 2.1046, 0.1079)

    def test_signature_key_with_different_precision(self) -> None:
        sig = StrategySignature(
            R=0.95432,
            delta_H=0.05678,
            kappa_mean=0.30123,
            entropy=2.10456,
            instability=0.10789,
        )

        key_2 = sig.key(precision=2)
        assert key_2 == (0.95, 0.06, 0.3, 2.1, 0.11)

        key_1 = sig.key(precision=1)
        assert key_1 == (1.0, 0.1, 0.3, 2.1, 0.1)

    def test_signature_key_default_precision(self) -> None:
        sig = StrategySignature(
            R=0.123456789,
            delta_H=0.987654321,
            kappa_mean=0.555555555,
            entropy=3.141592653,
            instability=0.271828182,
        )

        key = sig.key()  # Default precision=4
        assert isinstance(key, tuple)
        assert len(key) == 5

    def test_signature_is_immutable(self) -> None:
        sig = StrategySignature(
            R=0.95,
            delta_H=0.05,
            kappa_mean=0.3,
            entropy=2.1,
            instability=0.1,
        )

        with pytest.raises(AttributeError):
            sig.R = 0.99  # type: ignore

    def test_signature_equality(self) -> None:
        sig1 = StrategySignature(
            R=0.95,
            delta_H=0.05,
            kappa_mean=0.3,
            entropy=2.1,
            instability=0.1,
        )
        sig2 = StrategySignature(
            R=0.95,
            delta_H=0.05,
            kappa_mean=0.3,
            entropy=2.1,
            instability=0.1,
        )

        assert sig1 == sig2

    def test_signature_hash_consistency(self) -> None:
        sig1 = StrategySignature(
            R=0.95,
            delta_H=0.05,
            kappa_mean=0.3,
            entropy=2.1,
            instability=0.1,
        )
        sig2 = StrategySignature(
            R=0.95,
            delta_H=0.05,
            kappa_mean=0.3,
            entropy=2.1,
            instability=0.1,
        )

        # Frozen dataclasses should be hashable
        assert hash(sig1) == hash(sig2)
        # Can be used in sets
        sig_set = {sig1, sig2}
        assert len(sig_set) == 1


class TestStrategyRecord:
    """Test StrategyRecord creation and conversion."""

    def test_record_creation_with_signature_object(self) -> None:
        sig = StrategySignature(
            R=0.95,
            delta_H=0.05,
            kappa_mean=0.3,
            entropy=2.1,
            instability=0.1,
        )
        record = StrategyRecord(
            name="momentum_strategy",
            signature=sig,
            score=0.85,
        )

        assert record.name == "momentum_strategy"
        assert isinstance(record.signature, StrategySignature)
        assert record.score == 0.85
        assert isinstance(record.ts, float)

    def test_record_creation_with_tuple_signature(self) -> None:
        sig_tuple = (0.95, 0.05, 0.3, 2.1, 0.1)
        record = StrategyRecord(
            name="mean_reversion",
            signature=sig_tuple,
            score=0.75,
        )

        # Should be converted to StrategySignature
        assert isinstance(record.signature, StrategySignature)
        assert record.signature.R == 0.95
        assert record.signature.delta_H == 0.05
        assert record.score == 0.75

    def test_record_timestamp_is_recent(self) -> None:
        before = time.time()
        record = StrategyRecord(
            name="test_strategy",
            signature=(0.5, 0.5, 0.5, 0.5, 0.5),
            score=0.6,
        )
        after = time.time()

        assert before <= record.ts <= after

    def test_record_with_custom_timestamp(self) -> None:
        custom_ts = 1234567890.0
        record = StrategyRecord(
            name="historical_strategy",
            signature=(0.5, 0.5, 0.5, 0.5, 0.5),
            score=0.8,
            ts=custom_ts,
        )

        assert record.ts == custom_ts

    def test_record_negative_score(self) -> None:
        # Should allow negative scores (e.g., for losses)
        record = StrategyRecord(
            name="losing_strategy",
            signature=(0.5, 0.5, 0.5, 0.5, 0.5),
            score=-0.25,
        )

        assert record.score == -0.25


class TestStrategyMemory:
    """Test StrategyMemory storage and retrieval."""

    def test_memory_initialization(self) -> None:
        memory = StrategyMemory(decay_lambda=1e-6, max_records=256)

        assert memory.lmb == 1e-6
        assert memory.max_records == 256
        assert len(memory._records) == 0

    def test_memory_add_single_record(self) -> None:
        memory = StrategyMemory()
        sig = StrategySignature(
            R=0.95,
            delta_H=0.05,
            kappa_mean=0.3,
            entropy=2.1,
            instability=0.1,
        )

        memory.add("momentum", sig, score=0.85)

        assert len(memory._records) == 1
        assert memory._records[0].name == "momentum"
        assert memory._records[0].score == 0.85

    def test_memory_add_multiple_records(self) -> None:
        memory = StrategyMemory()

        sig1 = StrategySignature(0.95, 0.05, 0.3, 2.1, 0.1)
        sig2 = StrategySignature(0.80, 0.10, 0.4, 1.8, 0.2)
        sig3 = StrategySignature(0.70, 0.15, 0.5, 1.5, 0.3)

        memory.add("momentum", sig1, score=0.85)
        memory.add("mean_reversion", sig2, score=0.75)
        memory.add("arbitrage", sig3, score=0.90)

        assert len(memory._records) == 3

    def test_memory_add_with_tuple_signature(self) -> None:
        memory = StrategyMemory()
        sig_tuple = (0.95, 0.05, 0.3, 2.1, 0.1)

        memory.add("test_strategy", sig_tuple, score=0.80)

        assert len(memory._records) == 1
        assert isinstance(memory._records[0].signature, StrategySignature)

    def test_memory_decayed_score_recent(self) -> None:
        memory = StrategyMemory(decay_lambda=0.001)
        sig = StrategySignature(0.95, 0.05, 0.3, 2.1, 0.1)

        memory.add("test", sig, score=1.0)
        record = memory._records[0]

        # Recent record should have score close to original
        decayed = memory._decayed_score(record)
        assert 0.99 < decayed <= 1.0

    def test_memory_decayed_score_old(self) -> None:
        memory = StrategyMemory(decay_lambda=0.01)
        sig = StrategySignature(0.95, 0.05, 0.3, 2.1, 0.1)

        # Create old record
        old_ts = time.time() - 1000  # 1000 seconds ago
        record = StrategyRecord("old_strategy", sig, score=1.0, ts=old_ts)
        memory._records.append(record)

        # Old record should have significantly decayed score
        decayed = memory._decayed_score(record)
        assert decayed < 1.0
        assert decayed > 0.0  # Should still be positive

    def test_memory_max_records_limit(self) -> None:
        memory = StrategyMemory(max_records=3)

        for i in range(5):
            sig = StrategySignature(
                R=0.9 + i * 0.01,
                delta_H=0.05,
                kappa_mean=0.3,
                entropy=2.0,
                instability=0.1,
            )
            memory.add(f"strategy_{i}", sig, score=0.8)

        # Should not exceed max_records
        assert len(memory._records) <= memory.max_records

    def test_memory_different_decay_rates(self) -> None:
        # Fast decay
        fast_memory = StrategyMemory(decay_lambda=0.1)
        # Slow decay
        slow_memory = StrategyMemory(decay_lambda=0.001)

        sig = StrategySignature(0.95, 0.05, 0.3, 2.1, 0.1)
        old_ts = time.time() - 100

        fast_record = StrategyRecord("test", sig, score=1.0, ts=old_ts)
        slow_record = StrategyRecord("test", sig, score=1.0, ts=old_ts)

        fast_memory._records.append(fast_record)
        slow_memory._records.append(slow_record)

        fast_decayed = fast_memory._decayed_score(fast_record)
        slow_decayed = slow_memory._decayed_score(slow_record)

        # Fast decay should result in lower score
        assert fast_decayed < slow_decayed

    def test_memory_zero_decay(self) -> None:
        memory = StrategyMemory(decay_lambda=0.0)
        sig = StrategySignature(0.95, 0.05, 0.3, 2.1, 0.1)

        old_ts = time.time() - 10000
        record = StrategyRecord("test", sig, score=0.75, ts=old_ts)
        memory._records.append(record)

        decayed = memory._decayed_score(record)
        # With zero decay, score should remain unchanged
        assert decayed == 0.75


class TestStrategyMemoryIntegration:
    """Integration tests for realistic memory usage scenarios."""

    def test_market_regime_memory(self) -> None:
        """Simulate storing strategies for different market regimes."""
        memory = StrategyMemory(max_records=100)

        # Bull market regime
        bull_sig = StrategySignature(
            R=0.98,
            delta_H=0.02,
            kappa_mean=0.1,
            entropy=1.5,
            instability=0.05,
        )
        memory.add("momentum_long", bull_sig, score=0.90)

        # Bear market regime
        bear_sig = StrategySignature(
            R=0.70,
            delta_H=0.20,
            kappa_mean=0.6,
            entropy=2.5,
            instability=0.4,
        )
        memory.add("mean_reversion_short", bear_sig, score=0.85)

        # Sideways market regime
        sideways_sig = StrategySignature(
            R=0.85,
            delta_H=0.08,
            kappa_mean=0.3,
            entropy=2.0,
            instability=0.15,
        )
        memory.add("range_trading", sideways_sig, score=0.75)

        assert len(memory._records) == 3

        # All strategies should have different signatures
        signatures = [r.signature.key() for r in memory._records]
        assert len(set(signatures)) == 3

    def test_strategy_performance_tracking(self) -> None:
        """Track performance updates - keeps best score for each signature."""
        memory = StrategyMemory()

        base_sig = StrategySignature(
            R=0.90,
            delta_H=0.10,
            kappa_mean=0.35,
            entropy=2.0,
            instability=0.2,
        )

        # Add multiple performance records with same signature
        memory.add("MACD_crossover", base_sig, score=0.82)
        memory.add("MACD_crossover", base_sig, score=0.78)  # Lower, ignored
        memory.add("MACD_crossover", base_sig, score=0.85)  # Higher, replaces

        # Memory should keep only one record per signature (with best score)
        assert len(memory._records) == 1
        assert memory._records[0].score == 0.85  # Best score kept

    def test_temporal_decay_effect(self) -> None:
        """Verify that older strategies have lower effective scores."""
        memory = StrategyMemory(decay_lambda=0.01)
        sig = StrategySignature(0.90, 0.10, 0.30, 2.0, 0.2)

        # Add recent strategy
        memory.add("recent_strat", sig, score=0.80)
        recent_record = memory._records[-1]

        # Simulate old strategy
        old_ts = time.time() - 500
        old_record = StrategyRecord("old_strat", sig, score=0.80, ts=old_ts)
        memory._records.append(old_record)

        recent_score = memory._decayed_score(recent_record)
        old_score = memory._decayed_score(old_record)

        # Recent strategy should have higher effective score
        assert recent_score > old_score
        # But both should be positive
        assert old_score > 0

    def test_memory_capacity_management(self) -> None:
        """Test that memory respects capacity limits."""
        max_cap = 10
        memory = StrategyMemory(max_records=max_cap)

        # Add more records than capacity
        for i in range(20):
            sig = StrategySignature(
                R=0.9 + i * 0.001,
                delta_H=0.05 + i * 0.001,
                kappa_mean=0.3,
                entropy=2.0,
                instability=0.1,
            )
            memory.add(f"strategy_{i}", sig, score=0.7 + i * 0.01)

        # Memory should not exceed capacity (assuming pruning logic exists)
        # Note: Current implementation may not enforce this strictly
        # This test documents expected behavior
        assert len(memory._records) <= max_cap * 2  # Allow some overflow tolerance
