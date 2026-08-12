# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for experimental FractalPELMGPU memory backend.

These tests validate the experimental phase-aware retrieval backend.
Tests are marked with L3 as per the GeoSync test level mapping.
"""

from __future__ import annotations

import importlib.util

import numpy as np
import pytest

# Check if torch is available for conditional skipping
TORCH_AVAILABLE = importlib.util.find_spec("torch") is not None

pytestmark = pytest.mark.L3


@pytest.fixture
def fractal_pelm():
    """Create a FractalPELMGPU instance for testing."""
    if not TORCH_AVAILABLE:
        pytest.skip("PyTorch not available")

    from cortex_service.app.memory.experimental.fractal_pelm_gpu import FractalPELMGPU

    return FractalPELMGPU(dimension=64, capacity=1000, device="cpu", use_amp=False)


@pytest.fixture
def sample_vectors():
    """Generate sample vectors for testing."""
    np.random.seed(42)
    return np.random.randn(10, 64).astype(np.float32)


@pytest.fixture
def sample_phases():
    """Generate sample phases for testing."""
    return np.linspace(0, 2 * np.pi, 10).astype(np.float32)


class TestFractalPELMGPUImports:
    """Test import behavior and torch availability checking."""

    def test_is_torch_available_function(self):
        """Test that is_torch_available correctly reports torch status."""
        from cortex_service.app.memory.experimental.fractal_pelm_gpu import (
            is_torch_available,
        )

        result = is_torch_available()
        assert result == TORCH_AVAILABLE

    @pytest.mark.skipif(not TORCH_AVAILABLE, reason="Requires PyTorch")
    def test_module_can_be_imported_with_torch(self):
        """Test that module can be imported when torch is available."""
        from cortex_service.app.memory.experimental.fractal_pelm_gpu import (
            FractalPELMGPU,
        )

        assert FractalPELMGPU is not None


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="Requires PyTorch")
class TestFractalPELMGPUInitialization:
    """Test FractalPELMGPU initialization and validation."""

    def test_default_initialization(self):
        """Test default parameter initialization."""
        from cortex_service.app.memory.experimental.fractal_pelm_gpu import (
            FractalPELMGPU,
        )

        memory = FractalPELMGPU(device="cpu")

        assert memory.dimension == 384
        assert memory.capacity == 100_000
        assert memory.fractal_weight == 0.3
        assert memory.current_size == 0

    def test_custom_initialization(self):
        """Test custom parameter initialization."""
        from cortex_service.app.memory.experimental.fractal_pelm_gpu import (
            FractalPELMGPU,
        )

        memory = FractalPELMGPU(
            dimension=128,
            capacity=5000,
            device="cpu",
            use_amp=False,
            fractal_weight=0.5,
        )

        assert memory.dimension == 128
        assert memory.capacity == 5000
        assert memory.fractal_weight == 0.5

    def test_invalid_dimension_raises_error(self):
        """Test that invalid dimension raises ValueError."""
        from cortex_service.app.memory.experimental.fractal_pelm_gpu import (
            FractalPELMGPU,
        )

        with pytest.raises(ValueError, match="dimension must be positive"):
            FractalPELMGPU(dimension=0, device="cpu")

        with pytest.raises(ValueError, match="dimension must be positive"):
            FractalPELMGPU(dimension=-10, device="cpu")

    def test_invalid_capacity_raises_error(self):
        """Test that invalid capacity raises ValueError."""
        from cortex_service.app.memory.experimental.fractal_pelm_gpu import (
            FractalPELMGPU,
        )

        with pytest.raises(ValueError, match="capacity must be positive"):
            FractalPELMGPU(capacity=0, device="cpu")

    def test_invalid_fractal_weight_raises_error(self):
        """Test that invalid fractal_weight raises ValueError."""
        from cortex_service.app.memory.experimental.fractal_pelm_gpu import (
            FractalPELMGPU,
        )

        with pytest.raises(ValueError, match="fractal_weight must be in"):
            FractalPELMGPU(fractal_weight=-0.1, device="cpu")

        with pytest.raises(ValueError, match="fractal_weight must be in"):
            FractalPELMGPU(fractal_weight=1.5, device="cpu")


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="Requires PyTorch")
class TestBatchEntangle:
    """Test batch_entangle method."""

    def test_batch_entangle_with_numpy_arrays(self, fractal_pelm, sample_vectors, sample_phases):
        """Test entangling vectors using numpy arrays."""
        fractal_pelm.batch_entangle(sample_vectors, sample_phases)

        assert len(fractal_pelm) == 10
        assert fractal_pelm.current_size == 10

    def test_batch_entangle_with_torch_tensors(self, fractal_pelm, sample_vectors, sample_phases):
        """Test entangling vectors using torch tensors."""
        import torch

        vectors_t = torch.from_numpy(sample_vectors)
        phases_t = torch.from_numpy(sample_phases)

        fractal_pelm.batch_entangle(vectors_t, phases_t)

        assert len(fractal_pelm) == 10

    def test_batch_entangle_with_metadata(self, fractal_pelm, sample_vectors, sample_phases):
        """Test entangling vectors with metadata."""
        metadatas = [{"id": i, "label": f"entry_{i}"} for i in range(10)]

        fractal_pelm.batch_entangle(sample_vectors, sample_phases, metadatas)

        assert len(fractal_pelm) == 10

    def test_batch_entangle_mismatched_lengths_raises_error(self, fractal_pelm, sample_vectors):
        """Test that mismatched vectors and phases raises ValueError."""
        phases = np.linspace(0, np.pi, 5)  # Only 5 phases for 10 vectors

        with pytest.raises(ValueError, match="must have same length"):
            fractal_pelm.batch_entangle(sample_vectors, phases)

    def test_batch_entangle_wrong_dimension_raises_error(self, fractal_pelm, sample_phases):
        """Test that wrong vector dimension raises ValueError."""
        wrong_dim_vectors = np.random.randn(10, 32).astype(np.float32)

        with pytest.raises(ValueError, match="must have dimension"):
            fractal_pelm.batch_entangle(wrong_dim_vectors, sample_phases)

    def test_batch_entangle_enforces_capacity(self):
        """Test that capacity limit is enforced."""
        from cortex_service.app.memory.experimental.fractal_pelm_gpu import (
            FractalPELMGPU,
        )

        memory = FractalPELMGPU(dimension=16, capacity=10, device="cpu")

        # Add 15 entries (exceeds capacity of 10)
        vectors = np.random.randn(15, 16).astype(np.float32)
        phases = np.linspace(0, 2 * np.pi, 15)

        memory.batch_entangle(vectors, phases)

        assert len(memory) == 10  # Should be capped at capacity

    def test_batch_entangle_multiple_calls(self, fractal_pelm, sample_vectors, sample_phases):
        """Test multiple calls to batch_entangle accumulate entries."""
        fractal_pelm.batch_entangle(sample_vectors[:5], sample_phases[:5])
        assert len(fractal_pelm) == 5

        fractal_pelm.batch_entangle(sample_vectors[5:], sample_phases[5:])
        assert len(fractal_pelm) == 10


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="Requires PyTorch")
class TestRetrieve:
    """Test retrieve method."""

    def test_retrieve_from_empty_memory(self, fractal_pelm):
        """Test retrieval from empty memory returns empty list."""
        query = np.random.randn(64).astype(np.float32)

        results = fractal_pelm.retrieve(query, current_phase=0.0, top_k=5)

        assert results == []

    def test_retrieve_returns_expected_format(self, fractal_pelm, sample_vectors, sample_phases):
        """Test that retrieve returns correctly formatted results."""
        fractal_pelm.batch_entangle(sample_vectors, sample_phases)
        query = sample_vectors[0]

        results = fractal_pelm.retrieve(query, current_phase=sample_phases[0], top_k=3)

        assert len(results) == 3
        for score, vector, metadata in results:
            assert isinstance(score, float)
            assert 0.0 <= score <= 1.0
            assert isinstance(vector, np.ndarray)
            assert vector.shape == (64,)
            assert metadata is None  # No metadata was stored

    def test_retrieve_finds_exact_match(self, fractal_pelm, sample_vectors, sample_phases):
        """Test that exact match has highest score."""
        fractal_pelm.batch_entangle(sample_vectors, sample_phases)
        query = sample_vectors[0].copy()

        results = fractal_pelm.retrieve(query, current_phase=sample_phases[0], top_k=1)

        assert len(results) == 1
        score, vector, _ = results[0]
        # Score should be high for exact match
        assert score > 0.8
        # Vector should match query closely
        np.testing.assert_allclose(vector, query, rtol=1e-5)

    def test_retrieve_respects_top_k(self, fractal_pelm, sample_vectors, sample_phases):
        """Test that retrieve returns at most top_k results."""
        fractal_pelm.batch_entangle(sample_vectors, sample_phases)
        query = np.random.randn(64).astype(np.float32)

        results = fractal_pelm.retrieve(query, current_phase=0.0, top_k=3)

        assert len(results) == 3

    def test_retrieve_top_k_exceeds_size(self, fractal_pelm, sample_vectors, sample_phases):
        """Test retrieve when top_k exceeds memory size."""
        fractal_pelm.batch_entangle(sample_vectors[:3], sample_phases[:3])
        query = np.random.randn(64).astype(np.float32)

        results = fractal_pelm.retrieve(query, current_phase=0.0, top_k=10)

        assert len(results) == 3  # Should return all available

    def test_retrieve_returns_metadata(self, fractal_pelm, sample_vectors, sample_phases):
        """Test that metadata is returned when available."""
        metadatas = [{"id": i} for i in range(10)]
        fractal_pelm.batch_entangle(sample_vectors, sample_phases, metadatas)
        query = sample_vectors[0]

        results = fractal_pelm.retrieve(query, current_phase=sample_phases[0], top_k=1)

        assert len(results) == 1
        _, _, metadata = results[0]
        assert metadata is not None
        assert "id" in metadata

    def test_retrieve_scores_are_sorted(self, fractal_pelm, sample_vectors, sample_phases):
        """Test that results are sorted by descending score."""
        fractal_pelm.batch_entangle(sample_vectors, sample_phases)
        query = np.random.randn(64).astype(np.float32)

        results = fractal_pelm.retrieve(query, current_phase=0.0, top_k=5)

        scores = [r[0] for r in results]
        assert scores == sorted(scores, reverse=True)


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="Requires PyTorch")
class TestBatchRetrieve:
    """Test batch_retrieve method."""

    def test_batch_retrieve_multiple_queries(self, fractal_pelm, sample_vectors, sample_phases):
        """Test batch retrieval with multiple queries."""
        fractal_pelm.batch_entangle(sample_vectors, sample_phases)

        queries = sample_vectors[:3]
        query_phases = sample_phases[:3]

        results = fractal_pelm.batch_retrieve(queries, query_phases, top_k=2)

        assert len(results) == 3  # One result list per query
        for query_results in results:
            assert len(query_results) == 2  # top_k=2

    def test_batch_retrieve_with_torch_tensors(self, fractal_pelm, sample_vectors, sample_phases):
        """Test batch retrieval with torch tensors."""
        import torch

        fractal_pelm.batch_entangle(sample_vectors, sample_phases)

        queries = torch.from_numpy(sample_vectors[:2])
        query_phases = torch.from_numpy(sample_phases[:2])

        results = fractal_pelm.batch_retrieve(queries, query_phases, top_k=3)

        assert len(results) == 2

    def test_batch_retrieve_mismatched_lengths_raises_error(
        self, fractal_pelm, sample_vectors, sample_phases
    ):
        """Test that mismatched queries and phases raises ValueError."""
        fractal_pelm.batch_entangle(sample_vectors, sample_phases)

        queries = sample_vectors[:3]
        query_phases = sample_phases[:2]  # Wrong length

        with pytest.raises(ValueError, match="must have same length"):
            fractal_pelm.batch_retrieve(queries, query_phases, top_k=2)


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="Requires PyTorch")
class TestReset:
    """Test reset method."""

    def test_reset_clears_memory(self, fractal_pelm, sample_vectors, sample_phases):
        """Test that reset clears all entries."""
        fractal_pelm.batch_entangle(sample_vectors, sample_phases)
        assert len(fractal_pelm) == 10

        fractal_pelm.reset()

        assert len(fractal_pelm) == 0
        assert fractal_pelm.current_size == 0

    def test_reset_allows_new_entries(self, fractal_pelm, sample_vectors, sample_phases):
        """Test that entries can be added after reset."""
        fractal_pelm.batch_entangle(sample_vectors, sample_phases)
        fractal_pelm.reset()

        # Add new entries
        new_vectors = np.random.randn(5, 64).astype(np.float32)
        new_phases = np.linspace(0, np.pi, 5)

        fractal_pelm.batch_entangle(new_vectors, new_phases)

        assert len(fractal_pelm) == 5


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="Requires PyTorch")
class TestPhaseAwareRetrieval:
    """Test phase-aware retrieval behavior."""

    def test_phase_coherence_affects_ranking(self):
        """Test that phase coherence affects retrieval ranking."""
        from cortex_service.app.memory.experimental.fractal_pelm_gpu import (
            FractalPELMGPU,
        )

        memory = FractalPELMGPU(dimension=64, capacity=100, device="cpu", fractal_weight=0.0)

        np.random.seed(123)
        # Create two similar vectors with different phases
        base_vector = np.random.randn(64).astype(np.float32)
        v1 = base_vector + 0.01 * np.random.randn(64).astype(np.float32)
        v2 = base_vector + 0.01 * np.random.randn(64).astype(np.float32)

        # Store with different phases
        phase1 = 0.0
        phase2 = np.pi  # Opposite phase

        memory.batch_entangle(
            np.stack([v1, v2]),
            np.array([phase1, phase2], dtype=np.float32),
            [{"id": "v1"}, {"id": "v2"}],
        )

        # Query with phase 0.0 - should prefer v1
        query = base_vector
        results = memory.retrieve(query, current_phase=0.0, top_k=2)

        # Both should be returned, but v1 should rank higher due to phase coherence
        assert len(results) == 2
        top_metadata = results[0][2]
        assert top_metadata is not None
        assert top_metadata["id"] == "v1"


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="Requires PyTorch")
class TestFractalWeighting:
    """Test fractal weighting behavior."""

    def test_fractal_weight_zero_disables_fractal_scoring(self):
        """Test that fractal_weight=0 disables fractal component."""
        from cortex_service.app.memory.experimental.fractal_pelm_gpu import (
            FractalPELMGPU,
        )

        np.random.seed(456)
        vectors = np.random.randn(10, 64).astype(np.float32)
        phases = np.linspace(0, 2 * np.pi, 10)

        memory_with_fractal = FractalPELMGPU(
            dimension=64, capacity=100, device="cpu", fractal_weight=0.3
        )
        memory_without_fractal = FractalPELMGPU(
            dimension=64, capacity=100, device="cpu", fractal_weight=0.0
        )

        memory_with_fractal.batch_entangle(vectors, phases)
        memory_without_fractal.batch_entangle(vectors, phases)

        query = np.random.randn(64).astype(np.float32)
        query_phase = np.pi / 4

        results_with = memory_with_fractal.retrieve(query, query_phase, top_k=5)
        results_without = memory_without_fractal.retrieve(query, query_phase, top_k=5)

        # Scores should differ due to fractal component
        scores_with = [r[0] for r in results_with]
        scores_without = [r[0] for r in results_without]

        # Not identical (fractal weighting changes scores)
        assert not np.allclose(scores_with, scores_without)


@pytest.mark.skipif(not TORCH_AVAILABLE, reason="Requires PyTorch")
class TestNumericalStability:
    """Test numerical stability of the implementation."""

    def test_handles_zero_vectors(self, fractal_pelm):
        """Test handling of zero vectors."""
        zero_vectors = np.zeros((5, 64), dtype=np.float32)
        phases = np.linspace(0, np.pi, 5)

        fractal_pelm.batch_entangle(zero_vectors, phases)

        query = np.zeros(64, dtype=np.float32)
        results = fractal_pelm.retrieve(query, current_phase=0.0, top_k=3)

        # Should not crash, scores should be valid
        assert len(results) == 3
        for score, _, _ in results:
            assert np.isfinite(score)

    def test_handles_extreme_phases(self, fractal_pelm, sample_vectors):
        """Test handling of extreme phase values."""
        extreme_phases = np.array([0, 100 * np.pi, -100 * np.pi, 1e10, -1e10], dtype=np.float32)

        # Use only first 5 vectors
        fractal_pelm.batch_entangle(sample_vectors[:5], extreme_phases)

        query = sample_vectors[0]
        results = fractal_pelm.retrieve(query, current_phase=1e6, top_k=3)

        assert len(results) == 3
        for score, _, _ in results:
            assert np.isfinite(score)
            assert 0.0 <= score <= 1.0

    def test_handles_large_batch(self):
        """Test handling of large batch operations."""
        from cortex_service.app.memory.experimental.fractal_pelm_gpu import (
            FractalPELMGPU,
        )

        memory = FractalPELMGPU(dimension=128, capacity=10000, device="cpu")

        np.random.seed(789)
        vectors = np.random.randn(5000, 128).astype(np.float32)
        phases = np.random.uniform(0, 2 * np.pi, 5000).astype(np.float32)

        memory.batch_entangle(vectors, phases)

        assert len(memory) == 5000

        # Batch retrieve
        queries = np.random.randn(10, 128).astype(np.float32)
        query_phases = np.random.uniform(0, 2 * np.pi, 10).astype(np.float32)

        results = memory.batch_retrieve(queries, query_phases, top_k=20)

        assert len(results) == 10
        for query_results in results:
            assert len(query_results) == 20
