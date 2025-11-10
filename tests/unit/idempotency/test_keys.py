# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for idempotency key generation and fingerprinting."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from core.idempotency.keys import (
    IdempotencyKey,
    IdempotencyKeyFactory,
    canonical_dumps,
    fingerprint_payload,
)


def test_canonical_dumps_handles_dicts() -> None:
    """canonical_dumps should produce deterministic JSON for dictionaries."""
    payload1 = {"b": 2, "a": 1}
    payload2 = {"a": 1, "b": 2}
    
    result1 = canonical_dumps(payload1)
    result2 = canonical_dumps(payload2)
    
    # Order should be normalized
    assert result1 == result2
    assert result1 == '{"a":1,"b":2}'


def test_canonical_dumps_handles_nested_structures() -> None:
    """canonical_dumps should normalize nested structures."""
    payload = {
        "outer": {
            "z": 3,
            "y": 2,
            "x": 1,
        },
        "list": [1, 2, 3],
    }
    
    result = canonical_dumps(payload)
    
    # Should be deterministic
    assert '"outer":{"x":1,"y":2,"z":3}' in result
    assert '"list":[1,2,3]' in result


def test_canonical_dumps_handles_sets() -> None:
    """canonical_dumps should normalize sets into sorted lists."""
    payload1 = {"items": {3, 1, 2}}
    payload2 = {"items": {2, 3, 1}}
    
    result1 = canonical_dumps(payload1)
    result2 = canonical_dumps(payload2)
    
    # Sets should be sorted
    assert result1 == result2


def test_canonical_dumps_handles_datetime() -> None:
    """canonical_dumps should normalize datetime objects."""
    dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    payload = {"timestamp": dt}
    
    result = canonical_dumps(payload)
    
    assert "2024-01-15T10:30:00Z" in result


def test_canonical_dumps_handles_naive_datetime() -> None:
    """canonical_dumps should convert naive datetime to UTC."""
    dt = datetime(2024, 1, 15, 10, 30, 0)  # Naive
    payload = {"timestamp": dt}
    
    result = canonical_dumps(payload)
    
    # Should be converted to UTC
    assert "2024-01-15T10:30:00Z" in result


def test_canonical_dumps_handles_date() -> None:
    """canonical_dumps should handle date objects."""
    d = date(2024, 1, 15)
    payload = {"date": d}
    
    result = canonical_dumps(payload)
    
    assert "2024-01-15" in result


def test_canonical_dumps_handles_time() -> None:
    """canonical_dumps should handle time objects."""
    t = time(10, 30, 0, tzinfo=timezone.utc)
    payload = {"time": t}
    
    result = canonical_dumps(payload)
    
    assert "10:30:00Z" in result


def test_canonical_dumps_handles_decimal() -> None:
    """canonical_dumps should convert Decimal to float representation."""
    payload = {"price": Decimal("123.45")}
    
    result = canonical_dumps(payload)
    
    assert "123.45" in result


def test_canonical_dumps_handles_bytes() -> None:
    """canonical_dumps should convert bytes to hex."""
    payload = {"data": b"\x01\x02\x03"}
    
    result = canonical_dumps(payload)
    
    assert "010203" in result


def test_canonical_dumps_handles_uuid() -> None:
    """canonical_dumps should convert UUID to string."""
    uid = UUID("12345678-1234-5678-1234-567812345678")
    payload = {"id": uid}
    
    result = canonical_dumps(payload)
    
    assert "12345678-1234-5678-1234-567812345678" in result


def test_fingerprint_payload_is_deterministic() -> None:
    """fingerprint_payload should produce consistent hashes."""
    payload1 = {"a": 1, "b": 2}
    payload2 = {"b": 2, "a": 1}
    
    fp1 = fingerprint_payload(payload1)
    fp2 = fingerprint_payload(payload2)
    
    assert fp1 == fp2
    assert len(fp1) == 32  # 16 bytes = 32 hex chars


def test_fingerprint_payload_custom_digest_size() -> None:
    """fingerprint_payload should support custom digest sizes."""
    payload = {"test": "data"}
    
    fp8 = fingerprint_payload(payload, digest_size=8)
    fp16 = fingerprint_payload(payload, digest_size=16)
    
    assert len(fp8) == 16  # 8 bytes = 16 hex chars
    assert len(fp16) == 32  # 16 bytes = 32 hex chars


def test_idempotency_key_composite() -> None:
    """IdempotencyKey.composite should format correctly."""
    key = IdempotencyKey(
        service="trading",
        operation="place_order",
        request_id="req-123",
        operation_id="op-456",
        fingerprint="abc123",
    )
    
    composite = key.composite()
    
    assert composite == "trading:place_order:abc123"


def test_idempotency_key_factory_build() -> None:
    """IdempotencyKeyFactory should generate stable keys."""
    factory = IdempotencyKeyFactory()
    
    key = factory.build(
        service="trading",
        operation="place_order",
        dedupe_fields={"symbol": "AAPL", "quantity": 100},
    )
    
    assert key.service == "trading"
    assert key.operation == "place_order"
    assert key.request_id is not None
    assert key.operation_id is not None
    assert key.fingerprint is not None
    assert key.request_id == key.operation_id  # No attempt/nonce


def test_idempotency_key_factory_with_attempt() -> None:
    """IdempotencyKeyFactory should handle attempt numbers."""
    factory = IdempotencyKeyFactory()
    
    key1 = factory.build(
        service="trading",
        operation="place_order",
        dedupe_fields={"symbol": "AAPL"},
        attempt=1,
    )
    
    key2 = factory.build(
        service="trading",
        operation="place_order",
        dedupe_fields={"symbol": "AAPL"},
        attempt=2,
    )
    
    # Same request, different operations due to attempts
    assert key1.request_id == key2.request_id
    assert key1.operation_id != key2.operation_id


def test_idempotency_key_factory_with_nonce() -> None:
    """IdempotencyKeyFactory should handle nonces."""
    factory = IdempotencyKeyFactory()
    
    key1 = factory.build(
        service="trading",
        operation="place_order",
        dedupe_fields={"symbol": "AAPL"},
        nonce="session-123",
    )
    
    key2 = factory.build(
        service="trading",
        operation="place_order",
        dedupe_fields={"symbol": "AAPL"},
        nonce="session-456",
    )
    
    # Same request, different operations due to nonces
    assert key1.request_id == key2.request_id
    assert key1.operation_id != key2.operation_id


def test_idempotency_key_factory_with_nonce_and_attempt() -> None:
    """IdempotencyKeyFactory should handle both nonce and attempt."""
    factory = IdempotencyKeyFactory()
    
    key = factory.build(
        service="trading",
        operation="place_order",
        dedupe_fields={"symbol": "AAPL"},
        nonce="session-123",
        attempt=1,
    )
    
    assert key.operation_id != key.request_id


def test_idempotency_key_factory_empty_service_raises() -> None:
    """IdempotencyKeyFactory should reject empty service."""
    factory = IdempotencyKeyFactory()
    
    with pytest.raises(ValueError, match="service and operation must be provided"):
        factory.build(
            service="",
            operation="place_order",
            dedupe_fields={},
        )


def test_idempotency_key_factory_empty_operation_raises() -> None:
    """IdempotencyKeyFactory should reject empty operation."""
    factory = IdempotencyKeyFactory()
    
    with pytest.raises(ValueError, match="service and operation must be provided"):
        factory.build(
            service="trading",
            operation="",
            dedupe_fields={},
        )


def test_idempotency_key_factory_bulk() -> None:
    """IdempotencyKeyFactory.bulk should generate keys for batches."""
    factory = IdempotencyKeyFactory()
    
    items = [
        {"symbol": "AAPL", "quantity": 100},
        {"symbol": "GOOGL", "quantity": 50},
        {"symbol": "MSFT", "quantity": 75},
    ]
    
    keys = factory.bulk(
        service="trading",
        operation="place_orders",
        dedupe_items=items,
    )
    
    assert len(keys) == 3
    assert all(key.service == "trading" for key in keys)
    assert all(key.operation == "place_orders" for key in keys)
    
    # Each item should have unique fingerprint
    fingerprints = [key.fingerprint for key in keys]
    assert len(set(fingerprints)) == 3


def test_idempotency_key_factory_deterministic() -> None:
    """IdempotencyKeyFactory should produce same keys for same inputs."""
    factory = IdempotencyKeyFactory()
    
    payload = {"symbol": "AAPL", "quantity": 100}
    
    key1 = factory.build(
        service="trading",
        operation="place_order",
        dedupe_fields=payload,
    )
    
    key2 = factory.build(
        service="trading",
        operation="place_order",
        dedupe_fields=payload,
    )
    
    assert key1.request_id == key2.request_id
    assert key1.operation_id == key2.operation_id
    assert key1.fingerprint == key2.fingerprint


def test_idempotency_key_factory_custom_namespace() -> None:
    """IdempotencyKeyFactory should support custom namespaces."""
    namespace = UUID("12345678-1234-5678-1234-567812345678")
    factory = IdempotencyKeyFactory(namespace=namespace)
    
    key = factory.build(
        service="trading",
        operation="place_order",
        dedupe_fields={"symbol": "AAPL"},
    )
    
    assert key.request_id is not None
    assert key.operation_id is not None
