# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for StrategyMemory serialization and validation.

This module contains comprehensive tests for the StrategyMemory class,
covering serialization, validation, and invariant checking.
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from core.agent.memory import StrategyMemory, StrategyRecord, StrategySignature
from core.utils.memory_validation import (
    CorruptedStateError,
    InvariantError,
    compute_state_checksum,
)

# =============================================================================
# Test StrategySignature
# =============================================================================


class TestStrategySignature:
    """Tests for StrategySignature class."""

    def test_create_valid_signature(self) -> None:
        """Valid signature should be created successfully."""
        sig = StrategySignature(R=0.95, delta_H=0.05, kappa_mean=0.3, entropy=2.1, instability=0.1)
        assert sig.R == 0.95
        assert sig.delta_H == 0.05

    def test_reject_nan_in_signature(self) -> None:
        """NaN values should be rejected."""
        with pytest.raises(InvariantError, match="must be finite"):
            StrategySignature(
                R=float("nan"),
                delta_H=0.05,
                kappa_mean=0.3,
                entropy=2.1,
                instability=0.1,
            )

    def test_reject_inf_in_signature(self) -> None:
        """Infinity values should be rejected."""
        with pytest.raises(InvariantError, match="must be finite"):
            StrategySignature(
                R=float("inf"),
                delta_H=0.05,
                kappa_mean=0.3,
                entropy=2.1,
                instability=0.1,
            )

    def test_to_dict_roundtrip(self) -> None:
        """Serialization and deserialization should preserve values."""
        sig = StrategySignature(R=0.95, delta_H=0.05, kappa_mean=0.3, entropy=2.1, instability=0.1)
        sig_dict = sig.to_dict()
        restored = StrategySignature.from_dict(sig_dict)
        assert sig == restored

    def test_key_method(self) -> None:
        """Key method should return rounded tuple."""
        sig = StrategySignature(
            R=0.12345, delta_H=0.05, kappa_mean=0.3, entropy=2.1, instability=0.1
        )
        key = sig.key(precision=4)
        assert key == (0.1235, 0.05, 0.3, 2.1, 0.1)


# =============================================================================
# Test StrategyRecord
# =============================================================================


class TestStrategyRecord:
    """Tests for StrategyRecord class."""

    def test_create_valid_record(self) -> None:
        """Valid record should be created successfully."""
        sig = StrategySignature(R=0.95, delta_H=0.05, kappa_mean=0.3, entropy=2.1, instability=0.1)
        record = StrategyRecord(name="test", signature=sig, score=0.85, ts=time.time())
        assert record.name == "test"
        assert record.score == 0.85

    def test_create_record_from_tuple_signature(self) -> None:
        """Record should accept tuple signature and convert to StrategySignature."""
        record = StrategyRecord(name="test", signature=(0.95, 0.05, 0.3, 2.1, 0.1), score=0.85)
        assert isinstance(record.signature, StrategySignature)

    def test_reject_nan_score(self) -> None:
        """NaN score should be rejected."""
        with pytest.raises(InvariantError, match="score must be finite"):
            StrategyRecord(name="test", signature=(0.95, 0.05, 0.3, 2.1, 0.1), score=float("nan"))

    def test_reject_inf_score(self) -> None:
        """Infinity score should be rejected."""
        with pytest.raises(InvariantError, match="score must be finite"):
            StrategyRecord(name="test", signature=(0.95, 0.05, 0.3, 2.1, 0.1), score=float("inf"))

    def test_reject_negative_timestamp(self) -> None:
        """Negative timestamp should be rejected."""
        with pytest.raises(InvariantError, match="ts must be non-negative"):
            StrategyRecord(
                name="test",
                signature=(0.95, 0.05, 0.3, 2.1, 0.1),
                score=0.85,
                ts=-100.0,
            )

    def test_to_dict_roundtrip(self) -> None:
        """Serialization and deserialization should preserve values."""
        sig = StrategySignature(R=0.95, delta_H=0.05, kappa_mean=0.3, entropy=2.1, instability=0.1)
        record = StrategyRecord(name="test", signature=sig, score=0.85, ts=1000.0)
        record_dict = record.to_dict()
        restored = StrategyRecord.from_dict(record_dict)
        assert record.name == restored.name
        assert record.score == restored.score
        assert record.ts == restored.ts
        assert record.signature == restored.signature


# =============================================================================
# Test StrategyMemory
# =============================================================================


class TestStrategyMemory:
    """Tests for StrategyMemory class."""

    def test_create_memory_with_defaults(self) -> None:
        """Memory should be created with default parameters."""
        memory = StrategyMemory()
        assert memory.lmb == 1e-6
        assert memory.max_records == 256
        assert len(memory) == 0

    def test_create_memory_with_custom_params(self) -> None:
        """Memory should accept custom parameters."""
        memory = StrategyMemory(decay_lambda=1e-5, max_records=100)
        assert memory.lmb == 1e-5
        assert memory.max_records == 100

    def test_reject_negative_decay_lambda(self) -> None:
        """Negative decay_lambda should be rejected."""
        with pytest.raises(InvariantError, match="decay_lambda must be finite and >= 0"):
            StrategyMemory(decay_lambda=-1.0)

    def test_reject_nan_decay_lambda(self) -> None:
        """NaN decay_lambda should be rejected."""
        with pytest.raises(InvariantError, match="decay_lambda must be finite and >= 0"):
            StrategyMemory(decay_lambda=float("nan"))

    def test_reject_zero_max_records(self) -> None:
        """Zero max_records should be rejected."""
        with pytest.raises(InvariantError, match="max_records must be positive"):
            StrategyMemory(max_records=0)

    def test_add_record(self) -> None:
        """Adding a record should increase memory size."""
        memory = StrategyMemory()
        memory.add("test", (0.95, 0.05, 0.3, 2.1, 0.1), score=0.85)
        assert len(memory) == 1

    def test_add_rejects_nan_score(self) -> None:
        """Adding a record with NaN score should be rejected."""
        memory = StrategyMemory()
        with pytest.raises(InvariantError, match="score must be finite"):
            memory.add("test", (0.95, 0.05, 0.3, 2.1, 0.1), score=float("nan"))

    def test_capacity_enforcement(self) -> None:
        """Memory should not exceed max_records."""
        memory = StrategyMemory(max_records=3)
        for i in range(10):
            memory.add(f"strategy_{i}", (i * 0.1, 0.05, 0.3, 2.1, 0.1), score=float(i) * 0.1)
        assert len(memory) == 3

    def test_serialize_roundtrip(self) -> None:
        """Serialization and deserialization should preserve state."""
        memory = StrategyMemory(decay_lambda=1e-5, max_records=100)
        memory.add("test1", (0.95, 0.05, 0.3, 2.1, 0.1), score=0.85)
        memory.add("test2", (0.7, -0.02, 0.5, 1.8, 0.2), score=0.72)

        state = memory.to_dict()
        restored = StrategyMemory.from_dict(state, strict=True)

        assert restored.lmb == memory.lmb
        assert restored.max_records == memory.max_records
        assert len(restored) == len(memory)

    def test_serialize_includes_checksum(self) -> None:
        """Serialized state should include checksum."""
        memory = StrategyMemory()
        memory.add("test", (0.95, 0.05, 0.3, 2.1, 0.1), score=0.85)
        state = memory.to_dict()
        assert "_checksum" in state
        assert "state_version" in state

    def test_strict_mode_detects_checksum_mismatch(self) -> None:
        """Strict mode should raise on checksum mismatch."""
        memory = StrategyMemory()
        memory.add("test", (0.95, 0.05, 0.3, 2.1, 0.1), score=0.85)
        state = memory.to_dict()

        # Corrupt the checksum
        state["_checksum"] = "invalid_checksum"

        with pytest.raises(CorruptedStateError, match="checksum mismatch"):
            StrategyMemory.from_dict(state, strict=True)

    def test_recovery_mode_handles_checksum_mismatch(self) -> None:
        """Recovery mode should handle checksum mismatch gracefully."""
        memory = StrategyMemory()
        memory.add("test", (0.95, 0.05, 0.3, 2.1, 0.1), score=0.85)
        state = memory.to_dict()

        # Corrupt the checksum
        state["_checksum"] = "invalid_checksum"

        # Should not raise, but log a warning
        restored = StrategyMemory.from_dict(state, strict=False)
        assert len(restored) == 1

    def test_strict_mode_detects_corrupted_record(self) -> None:
        """Strict mode should raise on corrupted record."""
        memory = StrategyMemory()
        memory.add("test", (0.95, 0.05, 0.3, 2.1, 0.1), score=0.85)
        state = memory.to_dict()

        # Corrupt a record
        state["records"][0]["score"] = float("nan")
        del state["_checksum"]  # Remove checksum to focus on validation

        with pytest.raises(InvariantError):
            StrategyMemory.from_dict(state, strict=True)

    @pytest.mark.filterwarnings("ignore::RuntimeWarning")
    def test_recovery_mode_quarantines_corrupted_records(self) -> None:
        """Recovery mode should quarantine corrupted records."""
        memory = StrategyMemory()
        memory.add("test1", (0.95, 0.05, 0.3, 2.1, 0.1), score=0.85)
        memory.add("test2", (0.7, -0.02, 0.5, 1.8, 0.2), score=0.72)
        state = memory.to_dict()

        # Corrupt one record
        state["records"][0]["score"] = float("nan")
        del state["_checksum"]

        restored = StrategyMemory.from_dict(state, strict=False)
        assert len(restored) == 1  # One record quarantined
        assert restored.records[0].name == "test2"

    def test_decay_invariant_holds(self) -> None:
        """Decay should never increase score."""
        memory = StrategyMemory(decay_lambda=0.01)  # Fast decay for testing
        memory.add("test", (0.95, 0.05, 0.3, 2.1, 0.1), score=1.0)

        record = memory.records[0]
        original_score = record.score

        # Wait a bit and check decayed score
        time.sleep(0.01)
        decayed_score = memory._decayed_score(record)

        assert decayed_score <= original_score

    def test_topk_returns_sorted_by_decayed_score(self) -> None:
        """topk should return records sorted by decayed score."""
        memory = StrategyMemory()
        memory.add("high", (0.95, 0.05, 0.3, 2.1, 0.1), score=0.9)
        memory.add("low", (0.7, -0.02, 0.5, 1.8, 0.2), score=0.3)
        memory.add("medium", (0.8, 0.01, 0.4, 2.0, 0.15), score=0.6)

        top2 = memory.topk(k=2)
        assert len(top2) == 2
        assert top2[0].name == "high"
        assert top2[1].name == "medium"

    def test_validate_method(self) -> None:
        """validate() should check current state."""
        memory = StrategyMemory()
        memory.add("test", (0.95, 0.05, 0.3, 2.1, 0.1), score=0.85)
        memory.validate(strict=True)  # Should not raise

    def test_records_setter_validates_capacity(self) -> None:
        """Setting records should validate capacity constraint."""
        memory = StrategyMemory(max_records=2)

        records = [
            StrategyRecord(name=f"test{i}", signature=(i * 0.1, 0.05, 0.3, 2.1, 0.1), score=0.5)
            for i in range(5)
        ]

        with pytest.raises(InvariantError, match="Cannot set"):
            memory.records = records


# =============================================================================
# Property-based tests (without Hypothesis)
# =============================================================================


class TestPropertyBased:
    """Property-based tests using random inputs."""

    def test_random_operations_preserve_invariants(self) -> None:
        """Random operations should preserve memory invariants."""
        rng = np.random.default_rng(42)
        memory = StrategyMemory(decay_lambda=1e-6, max_records=50)

        # Perform random operations
        for _ in range(100):
            op = rng.choice(["add", "topk", "cleanup"])

            if op == "add":
                sig_values = rng.random(5).tolist()
                score = rng.random()
                memory.add(f"strategy_{rng.integers(1000)}", tuple(sig_values), score=score)
            elif op == "topk":
                k = rng.integers(1, 20)
                _ = memory.topk(int(k))
            elif op == "cleanup":
                min_score = rng.random() * 0.5
                memory.cleanup(min_score)

        # Validate invariants hold
        memory.validate(strict=True)
        assert len(memory) <= memory.max_records

    def test_serialize_roundtrip_with_random_data(self) -> None:
        """Random data should survive serialization roundtrip."""
        rng = np.random.default_rng(123)
        memory = StrategyMemory(decay_lambda=1e-6, max_records=50)

        # Add random records
        for i in range(20):
            sig_values = rng.random(5).tolist()
            score = rng.random()
            memory.add(f"strategy_{i}", tuple(sig_values), score=score)

        # Serialize and restore
        state = memory.to_dict()
        restored = StrategyMemory.from_dict(state, strict=True)

        # Check equivalence
        assert len(restored) == len(memory)
        for orig, rest in zip(memory.records, restored.records):
            assert orig.name == rest.name
            np.testing.assert_allclose(orig.score, rest.score)
            np.testing.assert_allclose(orig.ts, rest.ts)


# =============================================================================
# Fuzz tests
# =============================================================================


class TestFuzz:
    """Fuzz tests for corruption detection."""

    def test_byte_flip_in_serialized_state_detected(self) -> None:
        """Flipping bytes in serialized state should be detected."""
        import json

        memory = StrategyMemory()
        memory.add("test", (0.95, 0.05, 0.3, 2.1, 0.1), score=0.85)
        state = memory.to_dict()

        # Serialize to JSON and flip a byte
        json_str = json.dumps(state)
        json_bytes = bytearray(json_str.encode())

        # Flip a byte in the middle
        mid = len(json_bytes) // 2
        json_bytes[mid] ^= 0xFF

        # Try to parse (may fail with JSON error)
        try:
            corrupted = json.loads(json_bytes.decode())
            # If parsing succeeded, should detect via checksum
            with pytest.raises((CorruptedStateError, InvariantError, KeyError)):
                StrategyMemory.from_dict(corrupted, strict=True)
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Expected - corruption detected at JSON level
            pass

    def test_checksum_detects_field_mutation(self) -> None:
        """Mutating any field should change checksum."""
        memory = StrategyMemory()
        memory.add("test", (0.95, 0.05, 0.3, 2.1, 0.1), score=0.85)
        state = memory.to_dict()
        original_checksum = state["_checksum"]

        # Mutate the score
        state["records"][0]["score"] = 0.99

        new_checksum = compute_state_checksum(state)
        assert new_checksum != original_checksum
