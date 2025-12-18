# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Memory state validation utilities for production-grade memory hardening.

This module provides validation functions and exception classes to ensure
memory state integrity in TradePulse memory systems:

- StrategyMemory: Strategy episodic memory with decay
- FractalPELMGPU: Phase-entangled lattice memory

Key Features:
    - Invariant validation for all memory states
    - NaN/Inf detection and rejection
    - Checksum computation and verification
    - Strict vs recovery modes for corruption handling
    - Deterministic serialization support

Example:
    >>> from core.utils.memory_validation import (
    ...     validate_strategy_memory_state,
    ...     InvariantError,
    ... )
    >>> state = {"records": [...], "decay_lambda": 1e-6}
    >>> validate_strategy_memory_state(state, strict=True)  # raises on invalid
"""

from __future__ import annotations

import hashlib
import json
import logging
import warnings
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence

import numpy as np

logger = logging.getLogger(__name__)


class InvariantError(ValueError):
    """Raised when a memory state invariant is violated.

    Invariant errors indicate programming bugs or data corruption
    that violates the expected state contracts.
    """

    pass


class CorruptedStateError(ValueError):
    """Raised when memory state corruption is detected.

    This error is raised in strict mode when checksum verification
    fails or when recovery from corruption is not possible.
    """

    pass


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Result of memory state validation.

    Attributes:
        is_valid: True if all invariants hold
        violations: List of invariant violations found
        warnings: List of warnings (non-fatal issues)
        quarantined_indices: Indices of corrupted entries (recovery mode)
    """

    is_valid: bool
    violations: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    quarantined_indices: tuple[int, ...] = ()

    def raise_if_invalid(self) -> None:
        """Raise InvariantError if validation failed."""
        if not self.is_valid:
            raise InvariantError(
                f"Memory state validation failed: {'; '.join(self.violations)}"
            )


@dataclass
class ValidationContext:
    """Mutable context for accumulating validation results."""

    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    quarantined_indices: List[int] = field(default_factory=list)

    def add_violation(self, message: str) -> None:
        """Add a violation message."""
        self.violations.append(message)

    def add_warning(self, message: str) -> None:
        """Add a warning message."""
        self.warnings.append(message)

    def quarantine(self, index: int) -> None:
        """Mark an entry index as quarantined."""
        self.quarantined_indices.append(index)

    def to_result(self) -> ValidationResult:
        """Convert to immutable ValidationResult."""
        return ValidationResult(
            is_valid=len(self.violations) == 0,
            violations=tuple(self.violations),
            warnings=tuple(self.warnings),
            quarantined_indices=tuple(self.quarantined_indices),
        )


# =============================================================================
# Finite Value Validation
# =============================================================================


def assert_finite_float(
    value: float,
    name: str = "value",
    *,
    min_value: float | None = None,
    max_value: float | None = None,
) -> None:
    """Assert that a float value is finite and optionally within bounds.

    Args:
        value: The float value to validate.
        name: Name of the value for error messages.
        min_value: Optional minimum bound (inclusive).
        max_value: Optional maximum bound (inclusive).

    Raises:
        InvariantError: If the value is NaN, Inf, or out of bounds.
    """
    if not np.isfinite(value):
        raise InvariantError(f"{name} must be finite, got {value}")

    if min_value is not None and value < min_value:
        raise InvariantError(f"{name} must be >= {min_value}, got {value}")

    if max_value is not None and value > max_value:
        raise InvariantError(f"{name} must be <= {max_value}, got {value}")


def assert_finite_array(
    array: np.ndarray,
    name: str = "array",
    *,
    allow_empty: bool = True,
    expected_dtype: np.dtype | None = None,
) -> None:
    """Assert that all elements in a numpy array are finite.

    Args:
        array: The numpy array to validate.
        name: Name of the array for error messages.
        allow_empty: Whether empty arrays are allowed.
        expected_dtype: Optional expected dtype to check.

    Raises:
        InvariantError: If any element is NaN or Inf, or constraints violated.
    """
    if not isinstance(array, np.ndarray):
        raise InvariantError(f"{name} must be a numpy array, got {type(array).__name__}")

    if not allow_empty and array.size == 0:
        raise InvariantError(f"{name} must not be empty")

    if expected_dtype is not None and array.dtype != expected_dtype:
        raise InvariantError(
            f"{name} must have dtype {expected_dtype}, got {array.dtype}"
        )

    if array.size > 0 and not np.all(np.isfinite(array)):
        nan_count = np.sum(np.isnan(array))
        inf_count = np.sum(np.isinf(array))
        raise InvariantError(
            f"{name} contains non-finite values: {nan_count} NaN, {inf_count} Inf"
        )


# =============================================================================
# Checksum Utilities
# =============================================================================

# Current state format version for forward compatibility
STATE_VERSION = "1.0.0"


def compute_state_checksum(
    data: Dict[str, Any],
    *,
    algorithm: str = "sha256",
    exclude_keys: Sequence[str] = ("_checksum", "_computed_at"),
) -> str:
    """Compute a deterministic checksum for a state dictionary.

    The checksum covers all keys except those in exclude_keys,
    with deterministic key ordering for reproducibility.

    Args:
        data: State dictionary to checksum.
        algorithm: Hash algorithm to use (default: sha256).
        exclude_keys: Keys to exclude from checksum computation.

    Returns:
        Hex-encoded checksum string.
    """

    def _serialize_value(v: Any) -> Any:
        """Recursively serialize values for JSON encoding."""
        if isinstance(v, np.ndarray):
            return {
                "__type__": "ndarray",
                "data": v.tolist(),
                "dtype": str(v.dtype),
                "shape": v.shape,
            }
        elif isinstance(v, np.floating):
            return float(v)
        elif isinstance(v, np.integer):
            return int(v)
        elif isinstance(v, dict):
            return {k: _serialize_value(val) for k, val in sorted(v.items())}
        elif isinstance(v, (list, tuple)):
            return [_serialize_value(item) for item in v]
        return v

    # Filter and sort keys for determinism
    filtered = {
        k: _serialize_value(v) for k, v in sorted(data.items()) if k not in exclude_keys
    }

    # Serialize to JSON with sorted keys
    json_bytes = json.dumps(filtered, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )

    # Compute hash
    hasher = hashlib.new(algorithm)
    hasher.update(json_bytes)
    return hasher.hexdigest()


def verify_state_checksum(
    data: Dict[str, Any],
    expected_checksum: str,
    *,
    algorithm: str = "sha256",
    strict: bool = True,
) -> bool:
    """Verify that a state dictionary matches its expected checksum.

    Args:
        data: State dictionary to verify.
        expected_checksum: Expected checksum string.
        algorithm: Hash algorithm used (default: sha256).
        strict: If True, raise CorruptedStateError on mismatch.

    Returns:
        True if checksum matches, False otherwise (when strict=False).

    Raises:
        CorruptedStateError: If strict=True and checksum doesn't match.
    """
    actual_checksum = compute_state_checksum(data, algorithm=algorithm)

    if actual_checksum != expected_checksum:
        msg = (
            f"State checksum mismatch: expected {expected_checksum[:16]}..., "
            f"got {actual_checksum[:16]}... (algorithm: {algorithm})"
        )
        if strict:
            raise CorruptedStateError(msg)
        logger.warning(msg)
        return False

    return True


# =============================================================================
# StrategyMemory Validation
# =============================================================================


def validate_strategy_record(
    record: Dict[str, Any],
    index: int,
    ctx: ValidationContext,
    *,
    strict: bool = True,
) -> bool:
    """Validate a single strategy record.

    Args:
        record: Record dictionary to validate.
        index: Index of the record (for error messages).
        ctx: Validation context for accumulating results.
        strict: If True, any issue is a violation; else may quarantine.

    Returns:
        True if record is valid, False if it should be quarantined.
    """
    valid = True

    # Check required fields
    required = ("name", "signature", "score", "ts")
    for field_name in required:
        if field_name not in record:
            ctx.add_violation(f"Record {index}: missing required field '{field_name}'")
            valid = False

    if not valid:
        return False

    # Validate score
    score = record.get("score")
    if not isinstance(score, (int, float)):
        ctx.add_violation(f"Record {index}: score must be numeric, got {type(score)}")
        valid = False
    elif not np.isfinite(score):
        ctx.add_violation(f"Record {index}: score must be finite, got {score}")
        valid = False

    # Validate timestamp
    ts = record.get("ts")
    if not isinstance(ts, (int, float)):
        ctx.add_violation(f"Record {index}: ts must be numeric, got {type(ts)}")
        valid = False
    elif not np.isfinite(ts):
        ctx.add_violation(f"Record {index}: ts must be finite, got {ts}")
        valid = False
    elif ts < 0:
        ctx.add_violation(f"Record {index}: ts must be non-negative, got {ts}")
        valid = False

    # Validate signature
    sig = record.get("signature")
    if sig is not None:
        if isinstance(sig, dict):
            sig_fields = ("R", "delta_H", "kappa_mean", "entropy", "instability")
            for sig_field in sig_fields:
                if sig_field in sig:
                    val = sig[sig_field]
                    if not isinstance(val, (int, float)) or not np.isfinite(val):
                        ctx.add_violation(
                            f"Record {index}: signature.{sig_field} must be finite"
                        )
                        valid = False
        elif isinstance(sig, (list, tuple)) and len(sig) == 5:
            for i, val in enumerate(sig):
                if not isinstance(val, (int, float)) or not np.isfinite(val):
                    ctx.add_violation(
                        f"Record {index}: signature[{i}] must be finite, got {val}"
                    )
                    valid = False

    if not valid and not strict:
        ctx.quarantine(index)

    return valid


def validate_strategy_memory_state(
    state: Dict[str, Any],
    *,
    strict: bool = True,
) -> ValidationResult:
    """Validate a StrategyMemory state dictionary.

    Invariants checked:
    1. decay_lambda >= 0
    2. max_records > 0
    3. len(records) <= max_records
    4. All scores are finite
    5. All timestamps are finite and non-negative
    6. All signature fields are finite

    Args:
        state: State dictionary with keys:
            - records: List of record dicts
            - decay_lambda: Decay rate (>= 0)
            - max_records: Maximum record count (> 0)
        strict: If True, raise on any violation; else try to recover.

    Returns:
        ValidationResult with validation status and any issues found.

    Raises:
        InvariantError: If strict=True and validation fails.
    """
    ctx = ValidationContext()

    # Validate decay_lambda
    decay_lambda = state.get("decay_lambda", 0.0)
    if not isinstance(decay_lambda, (int, float)):
        ctx.add_violation(f"decay_lambda must be numeric, got {type(decay_lambda)}")
    elif not np.isfinite(decay_lambda):
        ctx.add_violation(f"decay_lambda must be finite, got {decay_lambda}")
    elif decay_lambda < 0:
        ctx.add_violation(f"decay_lambda must be >= 0, got {decay_lambda}")

    # Validate max_records
    max_records = state.get("max_records", 256)
    if not isinstance(max_records, int):
        ctx.add_violation(f"max_records must be int, got {type(max_records)}")
    elif max_records <= 0:
        ctx.add_violation(f"max_records must be > 0, got {max_records}")

    # Validate records
    records = state.get("records", [])
    if not isinstance(records, list):
        ctx.add_violation(f"records must be a list, got {type(records)}")
    else:
        # Check capacity constraint
        if isinstance(max_records, int) and len(records) > max_records:
            ctx.add_violation(
                f"len(records)={len(records)} exceeds max_records={max_records}"
            )

        # Validate each record
        for i, record in enumerate(records):
            if not isinstance(record, dict):
                ctx.add_violation(f"Record {i}: must be dict, got {type(record)}")
                if not strict:
                    ctx.quarantine(i)
                continue
            validate_strategy_record(record, i, ctx, strict=strict)

    result = ctx.to_result()

    if strict:
        result.raise_if_invalid()

    return result


# =============================================================================
# FractalPELMGPU Validation
# =============================================================================


def validate_pelm_entry(
    entry: Dict[str, Any],
    index: int,
    dimension: int,
    ctx: ValidationContext,
    *,
    strict: bool = True,
) -> bool:
    """Validate a single PELM memory entry.

    Args:
        entry: Entry dictionary with vector, phase, and optional metadata.
        index: Index of the entry (for error messages).
        dimension: Expected vector dimension.
        ctx: Validation context for accumulating results.
        strict: If True, any issue is a violation; else may quarantine.

    Returns:
        True if entry is valid, False if it should be quarantined.
    """
    valid = True

    # Validate vector
    vector = entry.get("vector")
    if vector is None:
        ctx.add_violation(f"Entry {index}: missing 'vector' field")
        valid = False
    else:
        if isinstance(vector, list):
            vector = np.array(vector)
        elif not isinstance(vector, np.ndarray):
            ctx.add_violation(
                f"Entry {index}: vector must be array, got {type(vector)}"
            )
            valid = False
            vector = None

        if vector is not None:
            if vector.size > 0 and not np.all(np.isfinite(vector)):
                ctx.add_violation(f"Entry {index}: vector contains NaN/Inf")
                valid = False

            if len(vector) != dimension:
                ctx.add_violation(
                    f"Entry {index}: vector dimension {len(vector)} != {dimension}"
                )
                valid = False

    # Validate phase
    phase = entry.get("phase")
    if phase is None:
        ctx.add_violation(f"Entry {index}: missing 'phase' field")
        valid = False
    elif not isinstance(phase, (int, float)):
        ctx.add_violation(f"Entry {index}: phase must be numeric, got {type(phase)}")
        valid = False
    elif not np.isfinite(phase):
        ctx.add_violation(f"Entry {index}: phase must be finite, got {phase}")
        valid = False

    # Validate metadata (optional)
    metadata = entry.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        ctx.add_violation(f"Entry {index}: metadata must be dict or None")
        valid = False

    if not valid and not strict:
        ctx.quarantine(index)

    return valid


def validate_pelm_state(
    state: Dict[str, Any],
    *,
    strict: bool = True,
) -> ValidationResult:
    """Validate a FractalPELMGPU state dictionary.

    Invariants checked:
    1. dimension > 0
    2. capacity > 0
    3. fractal_weight in [0, 1]
    4. len(entries) <= capacity
    5. All vectors are finite and have correct dimension
    6. All phases are finite
    7. All metadata entries are dict or None

    Args:
        state: State dictionary with keys:
            - dimension: Vector dimensionality
            - capacity: Maximum entry count
            - fractal_weight: Fractal scoring weight [0, 1]
            - entries: List of entry dicts (vector, phase, metadata)
        strict: If True, raise on any violation; else try to recover.

    Returns:
        ValidationResult with validation status and any issues found.

    Raises:
        InvariantError: If strict=True and validation fails.
    """
    ctx = ValidationContext()

    # Validate dimension
    dimension = state.get("dimension", 384)
    if not isinstance(dimension, int):
        ctx.add_violation(f"dimension must be int, got {type(dimension)}")
        dimension = 384  # fallback for further validation
    elif dimension <= 0:
        ctx.add_violation(f"dimension must be > 0, got {dimension}")

    # Validate capacity
    capacity = state.get("capacity", 100_000)
    if not isinstance(capacity, int):
        ctx.add_violation(f"capacity must be int, got {type(capacity)}")
    elif capacity <= 0:
        ctx.add_violation(f"capacity must be > 0, got {capacity}")

    # Validate fractal_weight
    fractal_weight = state.get("fractal_weight", 0.3)
    if not isinstance(fractal_weight, (int, float)):
        ctx.add_violation(f"fractal_weight must be numeric, got {type(fractal_weight)}")
    elif not np.isfinite(fractal_weight):
        ctx.add_violation(f"fractal_weight must be finite, got {fractal_weight}")
    elif not 0.0 <= fractal_weight <= 1.0:
        ctx.add_violation(f"fractal_weight must be in [0, 1], got {fractal_weight}")

    # Validate entries
    entries = state.get("entries", [])
    if not isinstance(entries, list):
        ctx.add_violation(f"entries must be a list, got {type(entries)}")
    else:
        # Check capacity constraint
        if isinstance(capacity, int) and len(entries) > capacity:
            ctx.add_violation(
                f"len(entries)={len(entries)} exceeds capacity={capacity}"
            )

        # Validate each entry
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                ctx.add_violation(f"Entry {i}: must be dict, got {type(entry)}")
                if not strict:
                    ctx.quarantine(i)
                continue
            validate_pelm_entry(entry, i, dimension, ctx, strict=strict)

    result = ctx.to_result()

    if strict:
        result.raise_if_invalid()

    return result


# =============================================================================
# Decay Invariant Validation
# =============================================================================


def validate_decay_invariant(
    original_score: float,
    decayed_score: float,
    *,
    tolerance: float = 1e-10,
) -> None:
    """Validate that decay never increases a score.

    This invariant ensures that time-based decay only reduces
    score values, never increases them (without an explicit event).

    Args:
        original_score: The original score value.
        decayed_score: The score after decay was applied.
        tolerance: Numerical tolerance for floating-point comparison.

    Raises:
        InvariantError: If decayed score exceeds original by more than tolerance.
    """
    assert_finite_float(original_score, "original_score")
    assert_finite_float(decayed_score, "decayed_score")

    if decayed_score > original_score + tolerance:
        raise InvariantError(
            f"Decay invariant violated: decayed_score={decayed_score:.6f} > "
            f"original_score={original_score:.6f} (tolerance={tolerance})"
        )


# =============================================================================
# State Recovery Utilities
# =============================================================================


def recover_strategy_memory_state(
    state: Dict[str, Any],
    validation_result: ValidationResult,
) -> Dict[str, Any]:
    """Attempt to recover a valid state from corrupted StrategyMemory state.

    This function removes quarantined records and returns a valid state.
    A warning is logged for each quarantined record.

    Args:
        state: The corrupted state dictionary.
        validation_result: ValidationResult with quarantined indices.

    Returns:
        A new state dict with corrupted records removed.
    """
    quarantined = set(validation_result.quarantined_indices)

    if quarantined:
        warnings.warn(
            f"Recovering StrategyMemory: quarantining {len(quarantined)} corrupted records",
            RuntimeWarning,
            stacklevel=2,
        )
        logger.warning(
            "StrategyMemory recovery: quarantined %d records at indices %s",
            len(quarantined),
            sorted(quarantined),
        )

    records = state.get("records", [])
    valid_records = [r for i, r in enumerate(records) if i not in quarantined]

    return {
        **state,
        "records": valid_records,
        "_recovered": True,
        "_quarantined_count": len(quarantined),
    }


def recover_pelm_state(
    state: Dict[str, Any],
    validation_result: ValidationResult,
) -> Dict[str, Any]:
    """Attempt to recover a valid state from corrupted PELM state.

    This function removes quarantined entries and returns a valid state.
    A warning is logged for each quarantined entry.

    Args:
        state: The corrupted state dictionary.
        validation_result: ValidationResult with quarantined indices.

    Returns:
        A new state dict with corrupted entries removed.
    """
    quarantined = set(validation_result.quarantined_indices)

    if quarantined:
        warnings.warn(
            f"Recovering PELM: quarantining {len(quarantined)} corrupted entries",
            RuntimeWarning,
            stacklevel=2,
        )
        logger.warning(
            "PELM recovery: quarantined %d entries at indices %s",
            len(quarantined),
            sorted(quarantined),
        )

    entries = state.get("entries", [])
    valid_entries = [e for i, e in enumerate(entries) if i not in quarantined]

    return {
        **state,
        "entries": valid_entries,
        "_recovered": True,
        "_quarantined_count": len(quarantined),
    }


__all__ = [
    # Exceptions
    "InvariantError",
    "CorruptedStateError",
    # Validation result types
    "ValidationResult",
    "ValidationContext",
    # Low-level assertions
    "assert_finite_float",
    "assert_finite_array",
    # Checksum utilities
    "STATE_VERSION",
    "compute_state_checksum",
    "verify_state_checksum",
    # StrategyMemory validation
    "validate_strategy_record",
    "validate_strategy_memory_state",
    # PELM validation
    "validate_pelm_entry",
    "validate_pelm_state",
    # Invariant validation
    "validate_decay_invariant",
    # Recovery utilities
    "recover_strategy_memory_state",
    "recover_pelm_state",
]
