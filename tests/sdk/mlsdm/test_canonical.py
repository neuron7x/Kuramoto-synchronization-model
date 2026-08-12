# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for canonical request and cache key computation.

These tests verify deterministic behavior of the canonicalization
and cache key computation for the MLSDM pipeline.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_module_directly(module_name: str, file_path: str):
    """Load a module directly from file path without triggering package __init__.py."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# Try to import normally first, fall back to direct load
try:
    from geosync.sdk.mlsdm.core.canonical import (
        CacheKeyFields,
        CanonicalRequest,
        canonical_request,
        compute_cache_key,
        normalize_text,
    )
except ImportError:
    # Load module directly to avoid SDK dependency chain
    test_dir = Path(__file__).parent
    canonical_path = (
        test_dir.parent.parent.parent
        / "src"
        / "geosync"
        / "sdk"
        / "mlsdm"
        / "core"
        / "canonical.py"
    )
    canonical_mod = _load_module_directly("test_canonical_mod", str(canonical_path))
    CacheKeyFields = canonical_mod.CacheKeyFields
    CanonicalRequest = canonical_mod.CanonicalRequest
    canonical_request = canonical_mod.canonical_request
    compute_cache_key = canonical_mod.compute_cache_key
    normalize_text = canonical_mod.normalize_text


class TestNormalizeText:
    """Tests for text normalization."""

    def test_strip_whitespace(self) -> None:
        """Strips leading and trailing whitespace."""
        assert normalize_text("  hello  ") == "hello"

    def test_collapse_whitespace(self) -> None:
        """Collapses multiple whitespace to single space."""
        assert normalize_text("hello   world") == "hello world"

    def test_normalize_tabs_and_newlines(self) -> None:
        """Normalizes tabs and newlines."""
        assert normalize_text("hello\t\nworld") == "hello world"

    def test_unicode_nfc_normalization(self) -> None:
        """Normalizes unicode to NFC form."""
        # Composed vs decomposed é
        composed = "café"
        decomposed = "cafe\u0301"
        assert normalize_text(composed) == normalize_text(decomposed)

    def test_empty_string(self) -> None:
        """Handles empty string."""
        assert normalize_text("") == ""


class TestCanonicalRequest:
    """Tests for canonical_request function."""

    def test_stable_order(self) -> None:
        """Dict order changes do not affect canonical representation."""
        config1 = {"a": 1, "b": 2, "c": 3}
        config2 = {"c": 3, "a": 1, "b": 2}
        config3 = {"b": 2, "c": 3, "a": 1}

        req1 = canonical_request("test", "1.0.0", config1)
        req2 = canonical_request("test", "1.0.0", config2)
        req3 = canonical_request("test", "1.0.0", config3)

        assert req1.cache_key == req2.cache_key == req3.cache_key
        assert req1.canonical_json == req2.canonical_json == req3.canonical_json

    def test_text_normalization_applied(self) -> None:
        """Input text is normalized before hashing."""
        req1 = canonical_request("  hello   world  ", "1.0.0")
        req2 = canonical_request("hello world", "1.0.0")

        assert req1.cache_key == req2.cache_key

    def test_different_text_different_key(self) -> None:
        """Different texts produce different keys."""
        req1 = canonical_request("hello", "1.0.0")
        req2 = canonical_request("world", "1.0.0")

        assert req1.cache_key != req2.cache_key

    def test_timestamps_excluded(self) -> None:
        """Timestamp fields in config do not affect cache key."""
        config1 = {"threshold": 0.5, "timestamp": 1234567890}
        config2 = {"threshold": 0.5, "timestamp": 9876543210}
        config3 = {"threshold": 0.5, "created_at": "2024-01-01"}
        config4 = {"threshold": 0.5}

        req1 = canonical_request("test", "1.0.0", config1)
        req2 = canonical_request("test", "1.0.0", config2)
        req3 = canonical_request("test", "1.0.0", config3)
        req4 = canonical_request("test", "1.0.0", config4)

        assert req1.cache_key == req2.cache_key == req3.cache_key == req4.cache_key

    def test_request_id_excluded(self) -> None:
        """Request ID fields are excluded from cache key."""
        config1 = {"threshold": 0.5, "request_id": "abc123"}
        config2 = {"threshold": 0.5, "request_id": "xyz789"}
        config3 = {"threshold": 0.5}

        req1 = canonical_request("test", "1.0.0", config1)
        req2 = canonical_request("test", "1.0.0", config2)
        req3 = canonical_request("test", "1.0.0", config3)

        assert req1.cache_key == req2.cache_key == req3.cache_key

    def test_policy_version_affects_key(self) -> None:
        """Policy version changes produce different keys."""
        req1 = canonical_request("test", "1.0.0")
        req2 = canonical_request("test", "1.1.0")

        assert req1.cache_key != req2.cache_key

    def test_model_id_affects_key(self) -> None:
        """Model ID changes produce different keys."""
        req1 = canonical_request("test", "1.0.0", model_id="gpt-4")
        req2 = canonical_request("test", "1.0.0", model_id="gpt-3.5")

        assert req1.cache_key != req2.cache_key

    def test_strict_mode_affects_key(self) -> None:
        """Strict mode flag affects cache key."""
        req1 = canonical_request("test", "1.0.0", strict_mode=False)
        req2 = canonical_request("test", "1.0.0", strict_mode=True)

        assert req1.cache_key != req2.cache_key

    def test_returns_canonical_request_type(self) -> None:
        """Returns CanonicalRequest dataclass."""
        req = canonical_request("test", "1.0.0")

        assert isinstance(req, CanonicalRequest)
        assert isinstance(req.fields, CacheKeyFields)
        assert len(req.cache_key) == 64  # SHA-256 hex
        assert req.canonical_json.startswith("{")


class TestCacheKeyFields:
    """Tests for CacheKeyFields dataclass."""

    def test_immutable(self) -> None:
        """CacheKeyFields is frozen (immutable)."""
        fields = CacheKeyFields(
            user_text="test",
            policy_version="1.0.0",
            config_hash="abcd1234",
        )

        with pytest.raises((AttributeError, TypeError)):  # FrozenInstanceError/AttributeError
            fields.user_text = "modified"  # type: ignore[misc]


class TestComputeCacheKey:
    """Tests for compute_cache_key function."""

    def test_deterministic(self) -> None:
        """Same inputs always produce same key."""
        fields = CacheKeyFields(
            user_text="test",
            policy_version="1.0.0",
            config_hash="abcd1234",
        )

        key1 = compute_cache_key(fields)
        key2 = compute_cache_key(fields)
        key3 = compute_cache_key(fields)

        assert key1 == key2 == key3

    def test_sha256_format(self) -> None:
        """Output is valid SHA-256 hex string."""
        fields = CacheKeyFields(
            user_text="test",
            policy_version="1.0.0",
            config_hash="abcd1234",
        )

        key = compute_cache_key(fields)

        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)


class TestNestedConfigCanonicalization:
    """Tests for nested config handling."""

    def test_nested_dict_sorted(self) -> None:
        """Nested dictionaries are sorted recursively."""
        config1 = {"outer": {"b": 2, "a": 1}}
        config2 = {"outer": {"a": 1, "b": 2}}

        req1 = canonical_request("test", "1.0.0", config1)
        req2 = canonical_request("test", "1.0.0", config2)

        assert req1.cache_key == req2.cache_key

    def test_nested_timestamps_excluded(self) -> None:
        """Timestamps in nested structures are excluded."""
        config1 = {"outer": {"value": 1, "updated_at": "2024-01-01"}}
        config2 = {"outer": {"value": 1}}

        req1 = canonical_request("test", "1.0.0", config1)
        req2 = canonical_request("test", "1.0.0", config2)

        assert req1.cache_key == req2.cache_key

    def test_list_order_preserved(self) -> None:
        """List order is preserved in canonicalization."""
        config1 = {"items": [1, 2, 3]}
        config2 = {"items": [3, 2, 1]}

        req1 = canonical_request("test", "1.0.0", config1)
        req2 = canonical_request("test", "1.0.0", config2)

        # Different list order = different key
        assert req1.cache_key != req2.cache_key
