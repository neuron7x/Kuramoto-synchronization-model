# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Canonicalization and cache key utilities for MLSDM pipeline.

This module provides deterministic request fingerprinting through:
- Canonical JSON serialization with stable key ordering
- Normalized whitespace handling for text inputs
- Secure SHA-256 based cache key computation
- Exclusion of non-deterministic fields (timestamps, random IDs)
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

__all__ = [
    "CanonicalRequest",
    "CacheKeyFields",
    "canonical_request",
    "compute_cache_key",
    "normalize_text",
]


# Version for cache key schema - bump when canonicalization logic changes
_CANONICAL_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class CacheKeyFields:
    """Fields included in cache key computation.

    Attributes:
        user_text: Normalized user input text.
        policy_version: Version of the policy/rules engine.
        config_hash: Hash of relevant configuration.
        model_id: Identifier of the model being used.
        strict_mode: Whether strict mode is enabled.
        canonical_version: Version of the canonicalization schema.
    """

    user_text: str
    policy_version: str
    config_hash: str
    model_id: str = "default"
    strict_mode: bool = False
    canonical_version: str = _CANONICAL_VERSION


@dataclass(frozen=True, slots=True)
class CanonicalRequest:
    """Canonical representation of a pipeline request.

    Attributes:
        fields: The cache key fields used for fingerprinting.
        cache_key: The computed SHA-256 cache key.
        canonical_json: The canonical JSON string representation.
    """

    fields: CacheKeyFields
    cache_key: str
    canonical_json: str


def normalize_text(text: str) -> str:
    """Normalize text for deterministic comparison.

    Applies the following normalizations:
    - Strip leading/trailing whitespace
    - Collapse multiple whitespace to single space
    - Normalize unicode to NFC form

    Args:
        text: Input text to normalize.

    Returns:
        Normalized text string.
    """
    import unicodedata

    # Normalize unicode
    normalized = unicodedata.normalize("NFC", text)
    # Strip and collapse whitespace
    normalized = re.sub(r"\s+", " ", normalized.strip())
    return normalized


def _serialize_canonical(data: Mapping[str, Any]) -> str:
    """Serialize data to canonical JSON form.

    Produces deterministic JSON output with:
    - Sorted keys at all nesting levels
    - No extraneous whitespace
    - Consistent float formatting

    Args:
        data: Dictionary to serialize.

    Returns:
        Canonical JSON string.
    """
    return json.dumps(
        data,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


def compute_cache_key(fields: CacheKeyFields) -> str:
    """Compute SHA-256 cache key from canonical fields.

    Args:
        fields: The cache key fields.

    Returns:
        Hexadecimal SHA-256 hash string.
    """
    data = {
        "user_text": fields.user_text,
        "policy_version": fields.policy_version,
        "config_hash": fields.config_hash,
        "model_id": fields.model_id,
        "strict_mode": fields.strict_mode,
        "canonical_version": fields.canonical_version,
    }
    canonical_json = _serialize_canonical(data)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def canonical_request(
    user_text: str,
    policy_version: str,
    config: Mapping[str, Any] | None = None,
    *,
    model_id: str = "default",
    strict_mode: bool = False,
) -> CanonicalRequest:
    """Create a canonical request representation.

    This function normalizes the input and computes a deterministic
    cache key suitable for caching and replay verification.

    Args:
        user_text: Raw user input text.
        policy_version: Version of the policy engine.
        config: Pipeline configuration (optional, hashed for fingerprint).
        model_id: Model identifier.
        strict_mode: Whether strict mode is enabled.

    Returns:
        CanonicalRequest with computed cache key.

    Example::

        req = canonical_request(
            user_text="Hello  world",
            policy_version="1.2.0",
            config={"threshold": 0.5},
        )
        print(req.cache_key)  # Deterministic hash
    """
    normalized_text = normalize_text(user_text)

    # Hash config for fingerprint (exclude non-deterministic fields)
    if config is None:
        config = {}

    # Remove any timestamp or random fields from config
    clean_config = _clean_config(config)
    config_json = _serialize_canonical(clean_config)
    config_hash = hashlib.sha256(config_json.encode("utf-8")).hexdigest()[:16]

    fields = CacheKeyFields(
        user_text=normalized_text,
        policy_version=policy_version,
        config_hash=config_hash,
        model_id=model_id,
        strict_mode=strict_mode,
    )

    cache_key = compute_cache_key(fields)

    # Build canonical JSON representation (for debugging/logging)
    canonical_data = {
        "user_text": fields.user_text,
        "policy_version": fields.policy_version,
        "config_hash": fields.config_hash,
        "model_id": fields.model_id,
        "strict_mode": fields.strict_mode,
        "canonical_version": fields.canonical_version,
    }
    canonical_json = _serialize_canonical(canonical_data)

    return CanonicalRequest(
        fields=fields,
        cache_key=cache_key,
        canonical_json=canonical_json,
    )


def _clean_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """Remove non-deterministic fields from config.

    Excludes fields that would cause non-deterministic cache keys:
    - Timestamps (created_at, updated_at, timestamp, etc.)
    - Random IDs (request_id, trace_id, etc.)
    - Runtime-specific fields

    Args:
        config: Original configuration dictionary.

    Returns:
        Cleaned configuration dictionary.
    """
    # Fields to exclude from canonicalization
    exclude_patterns = {
        "timestamp",
        "created_at",
        "updated_at",
        "request_id",
        "trace_id",
        "session_id",
        "run_id",
        "uuid",
        "_at",
        "_ts",
    }

    def is_excluded(key: str) -> bool:
        key_lower = key.lower()
        return any(pattern in key_lower for pattern in exclude_patterns)

    def clean_recursive(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: clean_recursive(v) for k, v in sorted(obj.items()) if not is_excluded(k)}
        if isinstance(obj, (list, tuple)):
            return [clean_recursive(item) for item in obj]
        return obj

    return clean_recursive(dict(config))
