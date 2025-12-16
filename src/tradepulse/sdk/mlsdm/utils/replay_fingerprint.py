"""Replay fingerprinting utilities for deterministic cache keys.

This module provides text normalization and cache key computation
for the MLSDM replay harness. All functions are designed to produce
stable, deterministic outputs regardless of ordering or whitespace.

Security Note: This module does NOT store raw prompts. Only hashes
are used in cache keys and reports.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

__all__ = [
    "PIPELINE_VERSION",
    "POLICY_VERSION",
    "normalize_text",
    "canonical_json",
    "sha256_hex",
    "compute_cache_key",
]

# Version constants for cache key stability
PIPELINE_VERSION: str = "0.1"
POLICY_VERSION: str = "policy-v1"

# Default stage versions for key components
DEFAULT_STAGE_VERSIONS: dict[str, str] = {
    "prefilter": "1.0.0",
    "policy": "1.0.0",
    "memory": "1.0.0",
    "postfilter": "1.0.0",
}

# Regex for collapsing whitespace
_WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Normalize text for stable fingerprinting.

    Applies the following transformations:
    1. Unicode NFC normalization
    2. Convert CRLF (\\r\\n) to LF (\\n)
    3. Collapse consecutive whitespace to single space
    4. Strip leading/trailing whitespace

    Args:
        text: The input text to normalize.

    Returns:
        Normalized text string.

    Example:
        >>> normalize_text("  Hello   World  ")
        'Hello World'
        >>> normalize_text("Line1\\r\\nLine2")
        'Line1 Line2'
    """
    # Step 1: Unicode NFC normalization
    normalized = unicodedata.normalize("NFC", text)

    # Step 2: Convert CRLF to LF
    normalized = normalized.replace("\r\n", "\n")

    # Step 3: Collapse whitespace (including newlines) to single space
    normalized = _WHITESPACE_PATTERN.sub(" ", normalized)

    # Step 4: Strip leading/trailing whitespace
    normalized = normalized.strip()

    return normalized


def canonical_json(obj: dict[str, Any]) -> bytes:
    """Serialize a dictionary to canonical JSON bytes.

    Produces a stable JSON representation:
    - Sorted keys
    - Compact separators (",", ":")
    - UTF-8 encoding
    - No NaN/Infinity (raises ValueError if present)

    Args:
        obj: Dictionary to serialize.

    Returns:
        UTF-8 encoded JSON bytes.

    Raises:
        ValueError: If obj contains NaN or Infinity floats.

    Example:
        >>> canonical_json({"b": 1, "a": 2})
        b'{"a":2,"b":1}'
    """
    return json.dumps(
        obj,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    """Compute SHA-256 hash of bytes and return as hex string.

    Args:
        data: Bytes to hash.

    Returns:
        64-character lowercase hex string.

    Example:
        >>> sha256_hex(b"hello")
        '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824'
    """
    return hashlib.sha256(data).hexdigest()


def compute_cache_key(
    *,
    text: str,
    strict_mode: bool = False,
    policy_version: str | None = None,
    stage_versions: dict[str, str] | None = None,
    config_subset: dict[str, Any] | None = None,
) -> str:
    """Compute a deterministic cache key for pipeline replay.

    The cache key is stable across:
    - Dict ordering (uses sorted keys)
    - Whitespace variations (normalizes text)
    - Unicode equivalents (NFC normalization)

    The key excludes:
    - Timestamps
    - Request IDs
    - Trace IDs
    - Raw prompt text (only hash is included)

    Args:
        text: The input text to fingerprint.
        strict_mode: Whether strict mode is enabled.
        policy_version: Version of the policy (default: POLICY_VERSION).
        stage_versions: Dict mapping stage names to versions.
        config_subset: Safe config subset (no secrets) to include.

    Returns:
        64-character hex cache key.

    Example:
        >>> key1 = compute_cache_key(text="hello", strict_mode=False)
        >>> key2 = compute_cache_key(text="  hello  ", strict_mode=False)
        >>> key1 == key2
        True
    """
    # Normalize the text
    normalized_text = normalize_text(text)

    # Hash the normalized text (never store raw prompts)
    text_hash = sha256_hex(normalized_text.encode("utf-8"))

    # Use defaults for missing parameters
    effective_policy_version = policy_version or POLICY_VERSION
    effective_stage_versions = stage_versions or DEFAULT_STAGE_VERSIONS
    effective_config_subset = config_subset or {}

    # Build the cache key payload
    payload: dict[str, Any] = {
        "normalized_text_hash": text_hash,
        "pipeline_version": PIPELINE_VERSION,
        "strict_mode": strict_mode,
        "policy_version": effective_policy_version,
        "stage_versions": effective_stage_versions,
        "config_fingerprint": sha256_hex(canonical_json(effective_config_subset)),
    }

    # Compute final hash
    return sha256_hex(canonical_json(payload))
