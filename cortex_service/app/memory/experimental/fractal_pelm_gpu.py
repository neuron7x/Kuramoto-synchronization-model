"""Experimental GPU/CPU backend for phase-aware vector retrieval.

This module provides FractalPELMGPU, an EXPERIMENTAL memory backend
that combines fractal geometry concepts with phase-aware retrieval.
It is designed for research and benchmarking, NOT for production use.

Key characteristics:
- Optional GPU acceleration via PyTorch (falls back to CPU if unavailable)
- Phase-aware similarity scoring combining cosine similarity with phase coherence
- Fractal-weighted scoring for multi-scale retrieval patterns
- Batch operations for efficient processing

Memory Hardening Features:
- State validation with invariant checking
- Deterministic serialization with checksum
- Strict vs recovery modes for corruption handling
- NaN/Inf rejection on all numeric values

EXPERIMENTAL WARNING:
This module is research-grade and may change without notice.
It requires PyTorch for operation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict

import numpy as np

from core.utils.memory_validation import (
    STATE_VERSION,
    InvariantError,
    compute_state_checksum,
    recover_pelm_state,
    validate_pelm_state,
    verify_state_checksum,
)

if TYPE_CHECKING:
    import torch

logger = logging.getLogger(__name__)


# Lazy import for torch to make it truly optional
_torch_module: Any = None
_TORCH_AVAILABLE: bool | None = None


def _get_torch() -> Any:
    """Lazily import and return the torch module.

    Raises
    ------
    ImportError
        If torch is not installed.
    """
    global _torch_module, _TORCH_AVAILABLE

    if _TORCH_AVAILABLE is False:
        raise ImportError(
            "FractalPELMGPU requires PyTorch. Install it with: pip install torch"
        )

    if _torch_module is None:
        try:
            import torch as _torch

            _torch_module = _torch
            _TORCH_AVAILABLE = True
        except ImportError as e:
            _TORCH_AVAILABLE = False
            raise ImportError(
                "FractalPELMGPU requires PyTorch. Install it with: pip install torch"
            ) from e

    return _torch_module


def is_torch_available() -> bool:
    """Check if PyTorch is available without importing it.

    Returns
    -------
    bool
        True if torch can be imported, False otherwise.
    """
    global _TORCH_AVAILABLE

    if _TORCH_AVAILABLE is not None:
        return _TORCH_AVAILABLE

    try:
        import torch  # noqa: F401

        _TORCH_AVAILABLE = True
    except ImportError:
        _TORCH_AVAILABLE = False

    return _TORCH_AVAILABLE


# Default scoring weights for combining similarity components
_DEFAULT_COSINE_WEIGHT = 0.7  # Weight for cosine similarity in base score
_DEFAULT_PHASE_WEIGHT = 0.3  # Weight for phase coherence in base score
_DEFAULT_FRACTAL_DECAY = 2.0  # Exponential decay factor for fractal rank weighting


@dataclass
class _MemoryEntry:
    """Internal storage for a single memory entry.

    Attributes:
        vector: Feature vector (must be finite)
        phase: Phase angle in radians (must be finite)
        metadata: Optional metadata dictionary
    """

    vector: np.ndarray
    phase: float
    metadata: dict | None = None

    def __post_init__(self) -> None:
        """Validate that vector and phase are finite."""
        if self.vector.size > 0 and not np.all(np.isfinite(self.vector)):
            raise InvariantError("_MemoryEntry vector contains NaN/Inf values")
        if not np.isfinite(self.phase):
            raise InvariantError(f"_MemoryEntry phase must be finite, got {self.phase}")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize entry to dictionary."""
        return {
            "vector": self.vector.tolist(),
            "phase": self.phase,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "_MemoryEntry":
        """Deserialize entry from dictionary."""
        vector = np.array(data["vector"], dtype=np.float32)
        return cls(
            vector=vector,
            phase=float(data["phase"]),
            metadata=data.get("metadata"),
        )


@dataclass
class FractalPELMGPU:
    """Experimental GPU/CPU backend for phase-aware vector retrieval.

    This class implements a phase-entangled lattice memory (PELM) with
    optional fractal-weighted scoring. It is designed for research and
    benchmarking purposes.

    The scoring function combines:
    1. Cosine similarity between query and stored vectors
    2. Phase coherence based on cosine of phase difference
    3. Optional fractal weighting for multi-scale patterns

    Parameters
    ----------
    dimension : int
        Dimensionality of stored vectors (default: 384).
    capacity : int
        Maximum number of entries to store (default: 100_000).
    device : str | None
        PyTorch device string ('cpu', 'cuda', 'cuda:0', etc.).
        If None, automatically selects CUDA if available.
    use_amp : bool
        Whether to use automatic mixed precision for GPU operations
        (default: True). Ignored on CPU.
    fractal_weight : float
        Weight for fractal scoring component (default: 0.3).
        Must be in [0, 1]. Setting to 0 disables fractal scoring.

    Raises
    ------
    ImportError
        If PyTorch is not installed.
    ValueError
        If dimension <= 0, capacity <= 0, or fractal_weight not in [0, 1].

    Examples
    --------
    >>> import numpy as np
    >>> memory = FractalPELMGPU(dimension=128, capacity=1000)
    >>> vectors = np.random.randn(10, 128).astype(np.float32)
    >>> phases = np.linspace(0, 2 * np.pi, 10)
    >>> memory.batch_entangle(vectors, phases)
    >>> query = np.random.randn(128).astype(np.float32)
    >>> results = memory.retrieve(query, current_phase=0.5, top_k=3)
    """

    dimension: int = 384
    capacity: int = 100_000
    device: str | None = None
    use_amp: bool = True
    fractal_weight: float = 0.3

    # Internal state (not exposed in constructor)
    _entries: list[_MemoryEntry] = field(default_factory=list, init=False, repr=False)
    _device_resolved: str = field(default="cpu", init=False, repr=False)
    _torch: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        """Validate parameters and initialize PyTorch device."""
        # Validation
        if self.dimension <= 0:
            raise ValueError(f"dimension must be positive, got {self.dimension}")
        if self.capacity <= 0:
            raise ValueError(f"capacity must be positive, got {self.capacity}")
        if not 0.0 <= self.fractal_weight <= 1.0:
            raise ValueError(
                f"fractal_weight must be in [0, 1], got {self.fractal_weight}"
            )

        # Initialize torch (will raise ImportError if not available)
        self._torch = _get_torch()

        # Resolve device
        if self.device is None:
            self._device_resolved = "cuda" if self._torch.cuda.is_available() else "cpu"
        else:
            self._device_resolved = self.device

        # Validate device
        try:
            self._torch.empty(0, device=self._device_resolved)
        except RuntimeError as e:
            raise ValueError(f"Invalid device '{self._device_resolved}': {e}") from e

        object.__setattr__(self, "_entries", [])

    def _to_tensor(
        self, data: np.ndarray | "torch.Tensor", dtype: "torch.dtype | None" = None
    ) -> Any:
        """Convert input to a torch tensor on the target device.

        Parameters
        ----------
        data : np.ndarray | torch.Tensor
            Input data to convert.
        dtype : torch.dtype | None
            Target dtype. If None, uses float32.

        Returns
        -------
        torch.Tensor
            Tensor on the configured device.
        """
        torch = self._torch
        if dtype is None:
            dtype = torch.float32

        if isinstance(data, np.ndarray):
            tensor = torch.from_numpy(data.astype(np.float32))
        else:
            tensor = data.clone()

        return tensor.to(device=self._device_resolved, dtype=dtype)

    def _to_numpy(self, tensor: "torch.Tensor") -> np.ndarray:
        """Convert torch tensor to numpy array.

        Parameters
        ----------
        tensor : torch.Tensor
            Input tensor.

        Returns
        -------
        np.ndarray
            Numpy array (always on CPU).
        """
        return tensor.detach().cpu().numpy()

    def _compute_phase_coherence(
        self,
        query_phase: float,
        stored_phases: "torch.Tensor",
    ) -> Any:
        """Compute phase coherence between query phase and stored phases.

        Phase coherence is defined as:
            coherence = (1 + cos(phase_diff)) / 2

        This maps the cosine of phase difference to [0, 1].

        Parameters
        ----------
        query_phase : float
            Query phase in radians.
        stored_phases : torch.Tensor
            Stored phases tensor of shape (N,).

        Returns
        -------
        torch.Tensor
            Coherence values of shape (N,) in [0, 1].
        """
        torch = self._torch
        phase_diff = stored_phases - query_phase
        coherence = (1.0 + torch.cos(phase_diff)) / 2.0
        return coherence

    def _compute_fractal_weight(
        self,
        similarities: "torch.Tensor",
    ) -> Any:
        """Compute fractal weighting based on similarity distribution.

        This applies a multi-scale weighting based on the relative
        ranking of similarities. Higher-ranked entries get a boost
        based on the fractal weight parameter.

        Parameters
        ----------
        similarities : torch.Tensor
            Raw similarity scores of shape (N,).

        Returns
        -------
        torch.Tensor
            Fractal weights of shape (N,) in [0, 1].
        """
        torch = self._torch
        n = similarities.shape[0]
        if n == 0:
            return torch.empty(0, device=self._device_resolved)

        # Rank-based weighting with exponential decay
        ranks = torch.argsort(torch.argsort(similarities, descending=True))
        # Normalize ranks to [0, 1] and apply exponential decay
        normalized_ranks = ranks.float() / max(n - 1, 1)
        weights = torch.exp(-_DEFAULT_FRACTAL_DECAY * normalized_ranks)

        # Normalize to [0, 1]
        if weights.max() > 0:
            weights = weights / weights.max()

        return weights

    def batch_entangle(
        self,
        vectors: np.ndarray | "torch.Tensor",
        phases: np.ndarray | "torch.Tensor",
        metadatas: list[dict | None] | None = None,
    ) -> None:
        """Store multiple vectors with their associated phases and metadata.

        If adding these entries would exceed capacity, the oldest entries
        are removed to make room.

        Parameters
        ----------
        vectors : np.ndarray | torch.Tensor
            Vectors to store, shape (N, dimension).
        phases : np.ndarray | torch.Tensor
            Phase values for each vector, shape (N,). Values in radians.
        metadatas : list[dict | None] | None
            Optional metadata for each vector. If None, no metadata is stored.

        Raises
        ------
        ValueError
            If vectors and phases have mismatched lengths, or if vectors
            have wrong dimensionality.
        """
        # Convert to tensors for validation
        vectors_t = self._to_tensor(vectors)
        phases_t = self._to_tensor(phases)

        # Validate shapes
        if vectors_t.ndim == 1:
            vectors_t = vectors_t.unsqueeze(0)
            phases_t = phases_t.unsqueeze(0) if phases_t.ndim == 0 else phases_t

        n_vectors = vectors_t.shape[0]
        n_phases = phases_t.shape[0]

        if n_vectors != n_phases:
            raise ValueError(
                f"vectors and phases must have same length, "
                f"got {n_vectors} and {n_phases}"
            )

        if vectors_t.shape[1] != self.dimension:
            raise ValueError(
                f"vectors must have dimension {self.dimension}, "
                f"got {vectors_t.shape[1]}"
            )

        if metadatas is not None and len(metadatas) != n_vectors:
            raise ValueError(
                f"metadatas must have same length as vectors, "
                f"got {len(metadatas)} and {n_vectors}"
            )

        # Convert back to numpy for storage (CPU-side)
        vectors_np = self._to_numpy(vectors_t)
        phases_np = self._to_numpy(phases_t)

        # Add entries
        for i in range(n_vectors):
            metadata = metadatas[i] if metadatas is not None else None
            entry = _MemoryEntry(
                vector=vectors_np[i].copy(),
                phase=float(phases_np[i]),
                metadata=metadata,
            )
            self._entries.append(entry)

        # Enforce capacity limit by removing oldest entries
        if len(self._entries) > self.capacity:
            excess = len(self._entries) - self.capacity
            self._entries = self._entries[excess:]

    def retrieve(
        self,
        query_vector: np.ndarray | "torch.Tensor",
        current_phase: float,
        top_k: int = 5,
    ) -> list[tuple[float, np.ndarray, dict | None]]:
        """Retrieve the top-k most similar entries for a query.

        Similarity is computed as a weighted combination of:
        1. Cosine similarity between vectors
        2. Phase coherence (based on cosine of phase difference)
        3. Optional fractal weighting

        Parameters
        ----------
        query_vector : np.ndarray | torch.Tensor
            Query vector of shape (dimension,).
        current_phase : float
            Current phase in radians for phase-aware retrieval.
        top_k : int
            Number of results to return (default: 5).

        Returns
        -------
        list[tuple[float, np.ndarray, dict | None]]
            List of (score, vector, metadata) tuples, sorted by
            descending score. Score is in [0, 1].

        Raises
        ------
        ValueError
            If query_vector has wrong dimensionality.
        """
        torch = self._torch

        # Handle query vector expansion
        if isinstance(query_vector, np.ndarray):
            query_expanded: np.ndarray | Any = query_vector.reshape(1, -1)
        else:
            query_expanded = query_vector.unsqueeze(0)

        # Handle phase - use tensor if torch input, numpy otherwise
        if isinstance(query_vector, np.ndarray):
            phase_input: np.ndarray | Any = np.array([current_phase])
        else:
            phase_input = torch.tensor([current_phase], dtype=torch.float32)

        results = self.batch_retrieve(
            query_vectors=query_expanded,
            current_phases=phase_input,
            top_k=top_k,
        )
        return results[0] if results else []

    def batch_retrieve(
        self,
        query_vectors: np.ndarray | "torch.Tensor",
        current_phases: np.ndarray | "torch.Tensor",
        top_k: int = 5,
    ) -> list[list[tuple[float, np.ndarray, dict | None]]]:
        """Retrieve the top-k most similar entries for multiple queries.

        Parameters
        ----------
        query_vectors : np.ndarray | torch.Tensor
            Query vectors of shape (M, dimension).
        current_phases : np.ndarray | torch.Tensor
            Phase values for each query, shape (M,).
        top_k : int
            Number of results per query (default: 5).

        Returns
        -------
        list[list[tuple[float, np.ndarray, dict | None]]]
            For each query, a list of (score, vector, metadata) tuples,
            sorted by descending score.

        Raises
        ------
        ValueError
            If query_vectors and current_phases have mismatched lengths,
            or if vectors have wrong dimensionality.
        """
        torch = self._torch

        if len(self._entries) == 0:
            # No entries to search
            query_t = self._to_tensor(query_vectors)
            if query_t.ndim == 1:
                query_t = query_t.unsqueeze(0)
            return [[] for _ in range(query_t.shape[0])]

        # Convert queries to tensors
        query_t = self._to_tensor(query_vectors)
        phases_t = self._to_tensor(current_phases)

        if query_t.ndim == 1:
            query_t = query_t.unsqueeze(0)
        if phases_t.ndim == 0:
            phases_t = phases_t.unsqueeze(0)

        n_queries = query_t.shape[0]
        n_phases = phases_t.shape[0]

        if n_queries != n_phases:
            raise ValueError(
                f"query_vectors and current_phases must have same length, "
                f"got {n_queries} and {n_phases}"
            )

        if query_t.shape[1] != self.dimension:
            raise ValueError(
                f"query_vectors must have dimension {self.dimension}, "
                f"got {query_t.shape[1]}"
            )

        # Build stored vectors matrix
        stored_vectors = np.stack([e.vector for e in self._entries], axis=0)
        stored_phases = np.array([e.phase for e in self._entries])

        stored_t = self._to_tensor(stored_vectors)
        stored_phases_t = self._to_tensor(stored_phases)

        # Normalize vectors for cosine similarity
        query_norm = torch.nn.functional.normalize(query_t, p=2, dim=1)
        stored_norm = torch.nn.functional.normalize(stored_t, p=2, dim=1)

        # Compute cosine similarity matrix: (M, N)
        use_amp = self.use_amp and self._device_resolved.startswith("cuda")

        if use_amp:
            with torch.cuda.amp.autocast():
                cosine_sim = torch.mm(query_norm, stored_norm.t())
        else:
            cosine_sim = torch.mm(query_norm, stored_norm.t())

        # Map cosine similarity from [-1, 1] to [0, 1]
        cosine_scores = (cosine_sim + 1.0) / 2.0

        # Compute results for each query
        all_results: list[list[tuple[float, np.ndarray, dict | None]]] = []

        for q_idx in range(n_queries):
            query_phase = float(phases_t[q_idx].item())
            sim_scores = cosine_scores[q_idx]

            # Compute phase coherence
            phase_coherence = self._compute_phase_coherence(
                query_phase, stored_phases_t
            )

            # Combine scores: weighted average of cosine and phase coherence
            base_weight = 1.0 - self.fractal_weight
            combined_scores = base_weight * (
                _DEFAULT_COSINE_WEIGHT * sim_scores
                + _DEFAULT_PHASE_WEIGHT * phase_coherence
            )

            # Add fractal weighting if enabled
            if self.fractal_weight > 0:
                fractal_weights = self._compute_fractal_weight(sim_scores)
                combined_scores = (
                    combined_scores + self.fractal_weight * fractal_weights * sim_scores
                )

            # Clamp to [0, 1]
            combined_scores = torch.clamp(combined_scores, 0.0, 1.0)

            # Get top-k indices
            k = min(top_k, len(self._entries))
            top_scores, top_indices = torch.topk(combined_scores, k)

            # Build result list
            query_results: list[tuple[float, np.ndarray, dict | None]] = []
            for score, idx in zip(
                self._to_numpy(top_scores), self._to_numpy(top_indices).astype(int)
            ):
                entry = self._entries[idx]
                query_results.append(
                    (float(score), entry.vector.copy(), entry.metadata)
                )

            all_results.append(query_results)

        return all_results

    def reset(self) -> None:
        """Clear all stored entries from memory."""
        self._entries.clear()

    def __len__(self) -> int:
        """Return the number of stored entries."""
        return len(self._entries)

    @property
    def current_size(self) -> int:
        """Return the current number of stored entries."""
        return len(self._entries)

    def validate(self, *, strict: bool = True) -> None:
        """Validate current memory state against invariants.

        Invariants checked:
        - dimension > 0
        - capacity > 0
        - fractal_weight in [0, 1]
        - len(entries) <= capacity
        - All vectors are finite and have correct dimension
        - All phases are finite

        Args:
            strict: If True, raise on any violation.

        Raises:
            InvariantError: If strict=True and validation fails.
        """
        state = self._to_state_dict()
        validate_pelm_state(state, strict=strict)

    def _to_state_dict(self) -> Dict[str, Any]:
        """Convert internal state to dictionary (without checksum)."""
        return {
            "dimension": self.dimension,
            "capacity": self.capacity,
            "fractal_weight": self.fractal_weight,
            "device": self._device_resolved,
            "use_amp": self.use_amp,
            "entries": [entry.to_dict() for entry in self._entries],
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize memory to dictionary with checksum.

        The returned dictionary includes:
            - state_version: Format version for compatibility
            - dimension: Vector dimensionality
            - capacity: Maximum entry count
            - fractal_weight: Fractal scoring weight
            - device: PyTorch device
            - use_amp: Mixed precision flag
            - entries: List of serialized entries
            - _checksum: SHA-256 checksum for integrity

        Returns:
            Serialized state dictionary.
        """
        state = self._to_state_dict()
        state["state_version"] = STATE_VERSION
        state["_checksum"] = compute_state_checksum(state)
        return state

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
        *,
        strict: bool = True,
        device: str | None = None,
    ) -> "FractalPELMGPU":
        """Deserialize memory from dictionary.

        Args:
            data: Serialized state dictionary.
            strict: If True, raise on checksum mismatch or validation failure.
                   If False, attempt recovery by quarantining corrupted entries.
            device: Override device setting (None uses value from state).

        Returns:
            Restored FractalPELMGPU instance.

        Raises:
            CorruptedStateError: If strict=True and checksum doesn't match.
            InvariantError: If strict=True and validation fails.
        """
        # Verify checksum if present
        if "_checksum" in data:
            verify_state_checksum(data, data["_checksum"], strict=strict)

        # Validate state
        result = validate_pelm_state(data, strict=strict)

        # Recover if needed - this modifies data in place
        if not result.is_valid and not strict:
            data = recover_pelm_state(data, result)
            # After recovery, indices are shifted so clear quarantine set
            quarantined: set[int] = set()
        else:
            quarantined = set(result.quarantined_indices)

        # Build memory instance
        memory = cls(
            dimension=data.get("dimension", 384),
            capacity=data.get("capacity", 100_000),
            device=device or data.get("device", "cpu"),
            use_amp=data.get("use_amp", True),
            fractal_weight=data.get("fractal_weight", 0.3),
        )

        # Restore entries
        entries_data = data.get("entries", [])

        for i, entry_data in enumerate(entries_data):
            if i in quarantined:
                continue  # Skip quarantined entries (only in non-recovered case)
            try:
                entry = _MemoryEntry.from_dict(entry_data)
                # Validate dimension
                if len(entry.vector) != memory.dimension:
                    if strict:
                        raise InvariantError(
                            f"Entry {i} dimension {len(entry.vector)} != {memory.dimension}"
                        )
                    logger.warning(
                        "Skipping entry %d: dimension mismatch (%d != %d)",
                        i,
                        len(entry.vector),
                        memory.dimension,
                    )
                    continue
                memory._entries.append(entry)
            except (KeyError, TypeError, InvariantError) as e:
                if strict:
                    raise
                logger.warning("Skipping corrupted entry %d: %s", i, e)
                # Skip corrupted entry in recovery mode

        return memory

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"FractalPELMGPU(dimension={self.dimension}, capacity={self.capacity}, "
            f"device={self._device_resolved!r}, current_size={len(self._entries)})"
        )


__all__ = ["FractalPELMGPU", "is_torch_available"]
