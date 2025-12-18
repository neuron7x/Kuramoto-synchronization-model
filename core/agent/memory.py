# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Strategy memory and adaptive learning infrastructure.

This module implements a memory system for trading agents that learn from past
performance and adapt their behavior over time:

- **StrategySignature**: Multi-dimensional fingerprint of market conditions
  (Ricci flow, Hurst exponent, curvature, entropy, instability)
- **StrategyRecord**: Performance records linking signatures to outcomes
- **StrategyMemory**: Episodic memory for caching successful strategies
- **AdaptiveLearning**: Context-aware strategy selection based on similarity

The memory system enables agents to recognize market regimes similar to those
they've seen before and apply strategies that worked well in those conditions,
implementing a form of case-based reasoning for trading.

Memory Hardening Features:
    - State validation with invariant checking
    - Deterministic serialization with checksum
    - Strict vs recovery modes for corruption handling
    - NaN/Inf rejection on all numeric values

Example:
    >>> from core.agent.memory import StrategyMemory, StrategySignature
    >>> memory = StrategyMemory(capacity=1000)
    >>> sig = StrategySignature(R=0.95, delta_H=0.05, kappa_mean=0.3,
    ...                         entropy=2.1, instability=0.1)
    >>> memory.store("momentum_strategy", sig, score=0.85)
    >>> # Serialize and restore
    >>> state = memory.to_dict()
    >>> memory2 = StrategyMemory.from_dict(state, strict=True)
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Tuple, Union

import numpy as np

from core.utils.memory_validation import (
    STATE_VERSION,
    InvariantError,
    compute_state_checksum,
    recover_strategy_memory_state,
    validate_decay_invariant,
    validate_strategy_memory_state,
    verify_state_checksum,
)


@dataclass(frozen=True)
class StrategySignature:
    """Multi-dimensional fingerprint of market conditions.

    All values must be finite (no NaN or Inf).

    Attributes:
        R: Ricci flow curvature measure
        delta_H: Hurst exponent change
        kappa_mean: Mean curvature
        entropy: Market entropy measure
        instability: Instability index
    """

    R: float
    delta_H: float
    kappa_mean: float
    entropy: float
    instability: float

    def __post_init__(self) -> None:
        """Validate that all signature values are finite."""
        for attr in ("R", "delta_H", "kappa_mean", "entropy", "instability"):
            value = getattr(self, attr)
            if not np.isfinite(value):
                raise InvariantError(f"StrategySignature.{attr} must be finite, got {value}")

    def key(self, precision: int = 4) -> Tuple[float, float, float, float, float]:
        rounded = tuple(
            round(value, precision)
            for value in (
                self.R,
                self.delta_H,
                self.kappa_mean,
                self.entropy,
                self.instability,
            )
        )
        return (rounded[0], rounded[1], rounded[2], rounded[3], rounded[4])

    def to_dict(self) -> Dict[str, float]:
        """Serialize signature to dictionary."""
        return {
            "R": self.R,
            "delta_H": self.delta_H,
            "kappa_mean": self.kappa_mean,
            "entropy": self.entropy,
            "instability": self.instability,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> "StrategySignature":
        """Deserialize signature from dictionary."""
        return cls(
            R=data["R"],
            delta_H=data["delta_H"],
            kappa_mean=data["kappa_mean"],
            entropy=data["entropy"],
            instability=data["instability"],
        )


@dataclass
class StrategyRecord:
    """Performance record linking a strategy to its outcome.

    All numeric values must be finite (no NaN or Inf).

    Attributes:
        name: Strategy name/identifier
        signature: Market condition fingerprint
        score: Performance score (must be finite)
        ts: Timestamp in seconds since epoch (must be non-negative)
    """

    name: str
    signature: Union[StrategySignature, Tuple[float, float, float, float, float]]
    score: float
    ts: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        # Convert tuple signature to StrategySignature
        if not isinstance(self.signature, StrategySignature):
            object.__setattr__(self, "signature", StrategySignature(*self.signature))

        # Validate score
        if not np.isfinite(self.score):
            raise InvariantError(f"StrategyRecord.score must be finite, got {self.score}")

        # Validate timestamp
        if not np.isfinite(self.ts):
            raise InvariantError(f"StrategyRecord.ts must be finite, got {self.ts}")
        if self.ts < 0:
            raise InvariantError(f"StrategyRecord.ts must be non-negative, got {self.ts}")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize record to dictionary."""
        sig = self.signature
        if isinstance(sig, StrategySignature):
            sig_dict = sig.to_dict()
        else:
            sig_dict = {
                "R": sig[0],
                "delta_H": sig[1],
                "kappa_mean": sig[2],
                "entropy": sig[3],
                "instability": sig[4],
            }
        return {
            "name": self.name,
            "signature": sig_dict,
            "score": self.score,
            "ts": self.ts,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StrategyRecord":
        """Deserialize record from dictionary."""
        sig_data = data["signature"]
        if isinstance(sig_data, dict):
            signature = StrategySignature.from_dict(sig_data)
        else:
            signature = StrategySignature(*sig_data)
        return cls(
            name=data["name"],
            signature=signature,
            score=data["score"],
            ts=data["ts"],
        )


class StrategyMemory:
    """Episodic memory for caching successful trading strategies.

    Stores StrategyRecord instances with time-based decay scoring.
    Supports serialization with checksum verification and recovery modes.

    Attributes:
        lmb: Decay rate (lambda) for score decay over time
        max_records: Maximum number of records to store

    Invariants:
        - decay_lambda >= 0
        - max_records > 0
        - len(records) <= max_records
        - All scores are finite
        - All timestamps are finite and non-negative
        - Decay never increases score (without explicit event)

    Example:
        >>> memory = StrategyMemory(decay_lambda=1e-6, max_records=256)
        >>> memory.add("momentum", (0.9, 0.05, 0.3, 2.1, 0.1), score=0.85)
        >>> state = memory.to_dict()
        >>> memory2 = StrategyMemory.from_dict(state)
    """

    def __init__(self, decay_lambda: float = 1e-6, max_records: int = 256):
        """Initialize StrategyMemory.

        Args:
            decay_lambda: Decay rate for score decay (must be >= 0).
            max_records: Maximum record count (must be > 0).

        Raises:
            InvariantError: If parameters violate constraints.
        """
        if not np.isfinite(decay_lambda) or decay_lambda < 0:
            raise InvariantError(f"decay_lambda must be finite and >= 0, got {decay_lambda}")
        if not isinstance(max_records, int) or max_records <= 0:
            raise InvariantError(f"max_records must be positive int, got {max_records}")

        self._records: List[StrategyRecord] = []
        self.lmb = decay_lambda
        self.max_records = max_records

    def _decayed_score(self, record: StrategyRecord) -> float:
        """Compute time-decayed score for a record.

        The decay follows exponential decay: score * exp(-lambda * age).

        Args:
            record: The record to compute decay for.

        Returns:
            Decayed score value.
        """
        age = time.time() - record.ts
        decayed = math.exp(-self.lmb * age) * record.score
        # Validate decay invariant (decay never increases score)
        validate_decay_invariant(record.score, decayed)
        return decayed

    def add(
        self,
        name: str,
        signature: Union[StrategySignature, Tuple[float, float, float, float, float]],
        score: float,
    ) -> None:
        """Add or update a strategy record.

        If a record with the same signature key exists and the new score
        is higher, the existing record is replaced.

        Args:
            name: Strategy name/identifier.
            signature: Market condition fingerprint.
            score: Performance score (must be finite).

        Raises:
            InvariantError: If score is not finite.
        """
        if not np.isfinite(score):
            raise InvariantError(f"score must be finite, got {score}")

        sig = (
            signature
            if isinstance(signature, StrategySignature)
            else StrategySignature(*signature)
        )
        key = sig.key()
        existing_index = next(
            (i for i, rec in enumerate(self._records) if rec.signature.key() == key),
            None,
        )
        record = StrategyRecord(name=name, signature=sig, score=score)
        if existing_index is None:
            self._records.append(record)
        elif score > self._records[existing_index].score:
            self._records[existing_index] = record
        if len(self._records) > self.max_records:
            self._evict()

    def topk(self, k: int = 5) -> List[StrategyRecord]:
        """Get the top-k records by decayed score.

        Args:
            k: Number of records to return.

        Returns:
            List of records sorted by decayed score (descending).
        """
        records = sorted(self._records, key=self._decayed_score, reverse=True)
        return records[:k]

    def cleanup(self, min_score: float = 0.0) -> None:
        """Remove records with decayed score below threshold.

        Args:
            min_score: Minimum decayed score to keep.
        """
        self._records = [
            record
            for record in self._records
            if self._decayed_score(record) > min_score
        ]

    def _evict(self) -> None:
        """Evict the record with the lowest decayed score."""
        if not self._records:
            return
        worst_index = min(
            range(len(self._records)),
            key=lambda i: self._decayed_score(self._records[i]),
        )
        self._records.pop(worst_index)

    @property
    def records(self) -> List[StrategyRecord]:
        """Get a copy of all records."""
        return list(self._records)

    @records.setter
    def records(self, values: Iterable[StrategyRecord]) -> None:
        """Set records with validation.

        Args:
            values: Iterable of StrategyRecord instances.

        Raises:
            TypeError: If any value is not a StrategyRecord.
            InvariantError: If capacity constraint would be violated.
        """
        converted: List[StrategyRecord] = []
        for record in values:
            if not isinstance(record, StrategyRecord):
                raise TypeError("records setter expects StrategyRecord instances")
            converted.append(record)

        if len(converted) > self.max_records:
            raise InvariantError(
                f"Cannot set {len(converted)} records; max_records={self.max_records}"
            )

        self._records = converted

    def validate(self, *, strict: bool = True) -> None:
        """Validate current memory state against invariants.

        Args:
            strict: If True, raise on any violation.

        Raises:
            InvariantError: If strict=True and validation fails.
        """
        state = self._to_state_dict()
        validate_strategy_memory_state(state, strict=strict)

    def _to_state_dict(self) -> Dict[str, Any]:
        """Convert internal state to dictionary (without checksum)."""
        return {
            "records": [r.to_dict() for r in self._records],
            "decay_lambda": self.lmb,
            "max_records": self.max_records,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize memory to dictionary with checksum.

        The returned dictionary includes:
            - state_version: Format version for compatibility
            - records: List of serialized records
            - decay_lambda: Decay rate
            - max_records: Capacity limit
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
    ) -> "StrategyMemory":
        """Deserialize memory from dictionary.

        Args:
            data: Serialized state dictionary.
            strict: If True, raise on checksum mismatch or validation failure.
                   If False, attempt recovery by quarantining corrupted records.

        Returns:
            Restored StrategyMemory instance.

        Raises:
            CorruptedStateError: If strict=True and checksum doesn't match.
            InvariantError: If strict=True and validation fails.
        """
        # Verify checksum if present
        if "_checksum" in data:
            verify_state_checksum(data, data["_checksum"], strict=strict)

        # Validate state
        result = validate_strategy_memory_state(data, strict=strict)

        # Recover if needed - this modifies data in place
        if not result.is_valid and not strict:
            data = recover_strategy_memory_state(data, result)
            # After recovery, indices are shifted so clear quarantine set
            quarantined: set[int] = set()
        else:
            quarantined = set(result.quarantined_indices)

        # Build memory instance
        memory = cls(
            decay_lambda=data.get("decay_lambda", 1e-6),
            max_records=data.get("max_records", 256),
        )

        # Restore records
        records_data = data.get("records", [])

        for i, record_data in enumerate(records_data):
            if i in quarantined:
                continue  # Skip quarantined records (only in non-recovered case)
            try:
                record = StrategyRecord.from_dict(record_data)
                memory._records.append(record)
            except (KeyError, TypeError, InvariantError):
                if strict:
                    raise
                # Skip corrupted record in recovery mode

        return memory

    def __len__(self) -> int:
        """Return number of stored records."""
        return len(self._records)

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"StrategyMemory(decay_lambda={self.lmb}, max_records={self.max_records}, "
            f"current_size={len(self._records)})"
        )
