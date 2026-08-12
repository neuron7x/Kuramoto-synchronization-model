# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for secure random number generation."""

import numpy as np
import pytest

from core.security.random import SecureNumpyRandom, SecureRandom


class TestSecureRandom:
    """Tests for cryptographically secure random number generation."""

    def test_randint_range(self):
        """Test random integer generation within range."""
        for _ in range(100):
            value = SecureRandom.randint(1, 10)
            assert 1 <= value <= 10
            assert isinstance(value, int)

    def test_randint_single_value(self):
        """Test randint with equal bounds."""
        value = SecureRandom.randint(5, 5)
        assert value == 5

    def test_randint_invalid_range(self):
        """Test randint with invalid range."""
        with pytest.raises(ValueError, match="Lower bound must be"):
            SecureRandom.randint(10, 5)

    def test_random_range(self):
        """Test random float generation."""
        for _ in range(100):
            value = SecureRandom.random()
            assert 0.0 <= value < 1.0
            assert isinstance(value, float)

    def test_uniform_range(self):
        """Test uniform distribution."""
        for _ in range(100):
            value = SecureRandom.uniform(10.0, 20.0)
            assert 10.0 <= value < 20.0
            assert isinstance(value, float)

    def test_uniform_invalid_range(self):
        """Test uniform with invalid range."""
        with pytest.raises(ValueError, match="Lower bound must be"):
            SecureRandom.uniform(10.0, 10.0)

    def test_choice(self):
        """Test random choice from sequence."""
        sequence = ["A", "B", "C", "D", "E"]

        for _ in range(100):
            value = SecureRandom.choice(sequence)
            assert value in sequence

    def test_choice_empty_sequence(self):
        """Test choice with empty sequence."""
        with pytest.raises(IndexError, match="Cannot choose from empty"):
            SecureRandom.choice([])

    def test_sample(self):
        """Test random sampling."""
        population = list(range(10))
        sample = SecureRandom.sample(population, 5)

        assert len(sample) == 5
        assert len(set(sample)) == 5  # All unique
        assert all(item in population for item in sample)

    def test_sample_full_population(self):
        """Test sampling entire population."""
        population = [1, 2, 3, 4, 5]
        sample = SecureRandom.sample(population, 5)

        assert len(sample) == 5
        assert set(sample) == set(population)

    def test_sample_invalid_size(self):
        """Test sample with size > population."""
        with pytest.raises(ValueError, match="cannot exceed population"):
            SecureRandom.sample([1, 2, 3], 5)

    def test_shuffle(self):
        """Test list shuffling."""
        original = list(range(10))
        shuffled = original.copy()

        SecureRandom.shuffle(shuffled)

        # Should have same elements
        assert set(shuffled) == set(original)
        assert len(shuffled) == len(original)

        # Should be different order (with high probability)
        # Note: There's a tiny chance they're the same, but extremely unlikely
        assert shuffled != original or len(original) <= 1

    def test_shuffle_inplace(self):
        """Test shuffle modifies list in place."""
        data = [1, 2, 3, 4, 5]
        original_id = id(data)

        SecureRandom.shuffle(data)

        assert id(data) == original_id  # Same object

    def test_token_bytes(self):
        """Test cryptographic token generation (bytes)."""
        token = SecureRandom.token_bytes(32)

        assert isinstance(token, bytes)
        assert len(token) == 32

        # Multiple calls should produce different tokens
        token2 = SecureRandom.token_bytes(32)
        assert token != token2

    def test_token_hex(self):
        """Test cryptographic token generation (hex)."""
        token = SecureRandom.token_hex(16)

        assert isinstance(token, str)
        assert len(token) == 32  # 16 bytes = 32 hex chars
        assert all(c in "0123456789abcdef" for c in token)

        # Multiple calls should produce different tokens
        token2 = SecureRandom.token_hex(16)
        assert token != token2

    def test_token_urlsafe(self):
        """Test URL-safe token generation."""
        token = SecureRandom.token_urlsafe(32)

        assert isinstance(token, str)
        assert len(token) > 0

        # Should be URL-safe (base64-url encoding)
        import string

        allowed_chars = string.ascii_letters + string.digits + "-_"
        assert all(c in allowed_chars for c in token)

    def test_randomness_distribution(self):
        """Test that values are reasonably distributed."""
        # Generate many random integers and check distribution
        samples = [SecureRandom.randint(1, 10) for _ in range(1000)]

        # Each value should appear at least once
        unique_values = set(samples)
        assert len(unique_values) >= 8  # Allow some variation

        # Check rough uniformity (no value should dominate)
        from collections import Counter

        counts = Counter(samples)
        for count in counts.values():
            assert 50 < count < 200  # Roughly 100 ± 50


class TestSecureNumpyRandom:
    """Tests for secure NumPy random number generation."""

    def test_random_scalar(self):
        """Test random scalar generation."""
        value = SecureNumpyRandom.random()

        assert isinstance(value, (float, np.floating))
        assert 0.0 <= value < 1.0

    def test_random_array(self):
        """Test random array generation."""
        arr = SecureNumpyRandom.random(size=10)

        assert isinstance(arr, np.ndarray)
        assert arr.shape == (10,)
        assert np.all((arr >= 0.0) & (arr < 1.0))

    def test_random_2d_array(self):
        """Test 2D random array generation."""
        arr = SecureNumpyRandom.random(size=(5, 3))

        assert isinstance(arr, np.ndarray)
        assert arr.shape == (5, 3)
        assert np.all((arr >= 0.0) & (arr < 1.0))

    def test_uniform_distribution(self):
        """Test uniform distribution."""
        arr = SecureNumpyRandom.uniform(10.0, 20.0, size=100)

        assert isinstance(arr, np.ndarray)
        assert arr.shape == (100,)
        assert np.all((arr >= 10.0) & (arr < 20.0))

    def test_integers(self):
        """Test random integer generation."""
        arr = SecureNumpyRandom.integers(1, 10, size=100)

        assert isinstance(arr, np.ndarray)
        assert arr.shape == (100,)
        assert np.all((arr >= 1) & (arr < 10))

    def test_integers_scalar(self):
        """Test scalar integer generation."""
        value = SecureNumpyRandom.integers(1, 10)

        assert isinstance(value, (int, np.integer))
        assert 1 <= value < 10

    def test_choice_from_array(self):
        """Test random choice from array."""
        population = np.array([1, 2, 3, 4, 5])
        sample = SecureNumpyRandom.choice(population, size=3, replace=False)

        assert isinstance(sample, np.ndarray)
        assert len(sample) == 3
        assert len(np.unique(sample)) == 3  # All unique
        assert all(val in population for val in sample)

    def test_choice_from_int(self):
        """Test random choice from range."""
        sample = SecureNumpyRandom.choice(10, size=5, replace=False)

        assert isinstance(sample, np.ndarray)
        assert len(sample) == 5
        assert all(0 <= val < 10 for val in sample)

    def test_shuffle(self):
        """Test array shuffling."""
        arr = np.arange(10)
        original = arr.copy()

        SecureNumpyRandom.shuffle(arr)

        # Should have same elements
        assert set(arr) == set(original)
        assert len(arr) == len(original)

    def test_uniqueness(self):
        """Test that different calls produce different results."""
        arr1 = SecureNumpyRandom.random(size=100)
        arr2 = SecureNumpyRandom.random(size=100)

        # Arrays should be different
        assert not np.array_equal(arr1, arr2)

    def test_statistical_properties(self):
        """Test basic statistical properties."""
        # Generate large sample
        samples = SecureNumpyRandom.random(size=10000)

        # Mean should be close to 0.5
        mean = np.mean(samples)
        assert 0.48 < mean < 0.52

        # Std should be close to 1/sqrt(12) ≈ 0.2887
        std = np.std(samples)
        assert 0.27 < std < 0.31
