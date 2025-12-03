# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for transformation pipeline: RawEvent -> NormalizedEvent -> MFNRequest.

Validates normalization, mapping, and error handling.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from mycelium_fractal_net.connectors.base import RawEvent
from mycelium_fractal_net.connectors.transform import (
    MappingError,
    MFNRequest,
    NormalizationError,
    NormalizedEvent,
    Transformer,
)


class TestNormalizedEvent:
    """Tests for NormalizedEvent model."""

    def test_create_minimal_event(self) -> None:
        """Test creating NormalizedEvent with minimal fields."""
        event = NormalizedEvent(
            source="test",
            timestamp=datetime.now(timezone.utc),
        )
        assert event.source == "test"
        assert event.event_type == "data"
        assert event.seeds == []
        assert event.grid_size == 64

    def test_create_with_seeds(self) -> None:
        """Test creating NormalizedEvent with seeds."""
        event = NormalizedEvent(
            source="test",
            timestamp=datetime.now(timezone.utc),
            seeds=[1.0, 2.0, 3.0],
            grid_size=128,
        )
        assert event.seeds == [1.0, 2.0, 3.0]
        assert event.grid_size == 128

    def test_seeds_coercion_from_ints(self) -> None:
        """Test seeds are coerced to floats."""
        event = NormalizedEvent(
            source="test",
            timestamp=datetime.now(timezone.utc),
            seeds=[1, 2, 3],  # type: ignore[list-item]
        )
        assert event.seeds == [1.0, 2.0, 3.0]
        assert all(isinstance(s, float) for s in event.seeds)

    def test_seeds_coercion_from_decimals(self) -> None:
        """Test seeds from Decimal values."""
        event = NormalizedEvent(
            source="test",
            timestamp=datetime.now(timezone.utc),
            seeds=[Decimal("1.5"), Decimal("2.5")],  # type: ignore[list-item]
        )
        assert event.seeds == [1.5, 2.5]

    def test_grid_size_bounds(self) -> None:
        """Test grid_size validation bounds."""
        # Valid at boundaries
        event_min = NormalizedEvent(
            source="test",
            timestamp=datetime.now(timezone.utc),
            grid_size=8,
        )
        assert event_min.grid_size == 8

        event_max = NormalizedEvent(
            source="test",
            timestamp=datetime.now(timezone.utc),
            grid_size=1024,
        )
        assert event_max.grid_size == 1024

        # Invalid - too small
        with pytest.raises(ValueError):
            NormalizedEvent(
                source="test",
                timestamp=datetime.now(timezone.utc),
                grid_size=4,
            )

        # Invalid - too large
        with pytest.raises(ValueError):
            NormalizedEvent(
                source="test",
                timestamp=datetime.now(timezone.utc),
                grid_size=2048,
            )


class TestMFNRequest:
    """Tests for MFNRequest model."""

    def test_create_feature_request(self) -> None:
        """Test creating feature extraction request."""
        request = MFNRequest(
            request_type="feature",
            request_id="feat-123",
            timestamp=datetime.now(timezone.utc),
            seeds=[1.0, 2.0],
            grid_size=64,
        )
        assert request.request_type == "feature"
        assert request.request_id == "feat-123"

    def test_create_simulation_request(self) -> None:
        """Test creating simulation request."""
        request = MFNRequest(
            request_type="simulation",
            request_id="sim-456",
            timestamp=datetime.now(timezone.utc),
            seeds=[1.0, 2.0, 3.0],
            grid_size=128,
            params={"iterations": 100},
        )
        assert request.request_type == "simulation"
        assert request.params["iterations"] == 100

    def test_invalid_request_type(self) -> None:
        """Test that invalid request_type is rejected."""
        with pytest.raises(ValueError):
            MFNRequest(
                request_type="invalid",  # type: ignore[arg-type]
                request_id="test",
                timestamp=datetime.now(timezone.utc),
            )


class TestTransformer:
    """Tests for Transformer pipeline."""

    def test_default_initialization(self) -> None:
        """Test Transformer with default settings."""
        transformer = Transformer()
        assert "seeds" in transformer.seed_fields
        assert transformer.grid_field == "grid_size"

    def test_custom_seed_fields(self) -> None:
        """Test Transformer with custom seed fields."""
        transformer = Transformer(seed_fields=["values", "data"])
        assert transformer.seed_fields == ["values", "data"]

    def test_normalize_basic_event(self) -> None:
        """Test normalizing a basic RawEvent."""
        transformer = Transformer()
        raw = RawEvent(
            source="test",
            timestamp=datetime.now(timezone.utc),
            payload={"seeds": [1.0, 2.0, 3.0], "grid_size": 128},
        )

        normalized = transformer.normalize(raw)

        assert normalized.source == "test"
        assert normalized.seeds == [1.0, 2.0, 3.0]
        assert normalized.grid_size == 128

    def test_normalize_extracts_from_configured_fields(self) -> None:
        """Test seed extraction from configured fields."""
        transformer = Transformer(seed_fields=["values"])
        raw = RawEvent(
            source="test",
            timestamp=datetime.now(timezone.utc),
            payload={"values": [10.0, 20.0]},
        )

        normalized = transformer.normalize(raw)
        assert normalized.seeds == [10.0, 20.0]

    def test_normalize_defaults_grid_size(self) -> None:
        """Test default grid_size when not in payload."""
        transformer = Transformer()
        raw = RawEvent(
            source="test",
            timestamp=datetime.now(timezone.utc),
            payload={},
        )

        normalized = transformer.normalize(raw)
        assert normalized.grid_size == 64  # default

    def test_normalize_clamps_grid_size(self) -> None:
        """Test grid_size is clamped to valid range."""
        transformer = Transformer()

        # Too small
        raw_small = RawEvent(
            source="test",
            timestamp=datetime.now(timezone.utc),
            payload={"grid_size": 2},
        )
        normalized = transformer.normalize(raw_small)
        assert normalized.grid_size == 8  # clamped to min

        # Too large
        raw_large = RawEvent(
            source="test",
            timestamp=datetime.now(timezone.utc),
            payload={"grid_size": 5000},
        )
        normalized = transformer.normalize(raw_large)
        assert normalized.grid_size == 1024  # clamped to max

    def test_normalize_preserves_raw_payload(self) -> None:
        """Test that raw payload is preserved."""
        transformer = Transformer()
        raw = RawEvent(
            source="test",
            timestamp=datetime.now(timezone.utc),
            payload={"key": "value", "nested": {"a": 1}},
        )

        normalized = transformer.normalize(raw)
        assert normalized.raw_payload == raw.payload

    def test_normalize_extracts_event_type(self) -> None:
        """Test event_type extraction."""
        transformer = Transformer()

        # Valid event_type
        raw = RawEvent(
            source="test",
            timestamp=datetime.now(timezone.utc),
            payload={"event_type": "signal"},
        )
        normalized = transformer.normalize(raw)
        assert normalized.event_type == "signal"

        # Invalid event_type defaults to data
        raw_invalid = RawEvent(
            source="test",
            timestamp=datetime.now(timezone.utc),
            payload={"event_type": "unknown"},
        )
        normalized_invalid = transformer.normalize(raw_invalid)
        assert normalized_invalid.event_type == "data"

    def test_normalize_extracts_params(self) -> None:
        """Test params extraction from payload."""
        transformer = Transformer(param_fields=["iterations", "threshold"])
        raw = RawEvent(
            source="test",
            timestamp=datetime.now(timezone.utc),
            payload={
                "iterations": 100,
                "threshold": 0.5,
                "other": "ignored",
            },
        )

        normalized = transformer.normalize(raw)
        assert normalized.params["iterations"] == 100
        assert normalized.params["threshold"] == 0.5
        assert "other" not in normalized.params

    def test_to_feature_request(self) -> None:
        """Test mapping NormalizedEvent to feature request."""
        transformer = Transformer()
        normalized = NormalizedEvent(
            source="test",
            timestamp=datetime.now(timezone.utc),
            seeds=[1.0, 2.0],
            grid_size=64,
        )

        request = transformer.to_feature_request(normalized, request_id="feat-001")

        assert request.request_type == "feature"
        assert request.request_id == "feat-001"
        assert request.seeds == [1.0, 2.0]
        assert request.source_event is normalized

    def test_to_feature_request_auto_id(self) -> None:
        """Test auto-generated request ID."""
        transformer = Transformer()
        normalized = NormalizedEvent(
            source="api",
            timestamp=datetime.now(timezone.utc),
        )

        request = transformer.to_feature_request(normalized)
        assert request.request_id.startswith("feat-api-")

    def test_to_simulation_request(self) -> None:
        """Test mapping NormalizedEvent to simulation request."""
        transformer = Transformer()
        normalized = NormalizedEvent(
            source="test",
            timestamp=datetime.now(timezone.utc),
            seeds=[1.0, 2.0, 3.0],
            grid_size=128,
            params={"iterations": 50},
        )

        request = transformer.to_simulation_request(normalized, request_id="sim-001")

        assert request.request_type == "simulation"
        assert request.request_id == "sim-001"
        assert request.grid_size == 128
        assert request.params["iterations"] == 50

    def test_to_simulation_request_auto_id(self) -> None:
        """Test auto-generated simulation request ID."""
        transformer = Transformer()
        normalized = NormalizedEvent(
            source="sensor",
            timestamp=datetime.now(timezone.utc),
        )

        request = transformer.to_simulation_request(normalized)
        assert request.request_id.startswith("sim-sensor-")


class TestNormalizationError:
    """Tests for NormalizationError exception."""

    def test_error_message_minimal(self) -> None:
        """Test error message with minimal info."""
        error = NormalizationError(reason="Invalid data")
        assert "Invalid data" in str(error)

    def test_error_message_with_source(self) -> None:
        """Test error message includes source."""
        error = NormalizationError(reason="Parse failed", source="api_source")
        assert "api_source" in str(error)
        assert error.source == "api_source"

    def test_error_message_with_field(self) -> None:
        """Test error message includes field."""
        error = NormalizationError(
            reason="Invalid value",
            source="test",
            field="grid_size",
        )
        assert "grid_size" in str(error)
        assert error.field == "grid_size"


class TestMappingError:
    """Tests for MappingError exception."""

    def test_error_message_minimal(self) -> None:
        """Test error message with minimal info."""
        error = MappingError(reason="Mapping failed")
        assert "Mapping failed" in str(error)

    def test_error_message_with_request_type(self) -> None:
        """Test error message includes request type."""
        error = MappingError(reason="Invalid seeds", request_type="feature")
        assert "feature" in str(error)
        assert error.request_type == "feature"


class TestTransformerErrorHandling:
    """Tests for error handling in transformer."""

    def test_normalize_handles_various_inputs(self) -> None:
        """Test that normalize handles various input formats leniently."""
        transformer = Transformer()

        # Normalize is lenient - it extracts what it can
        raw = RawEvent(
            source="test",
            timestamp=datetime.now(timezone.utc),
            payload={"seeds": "not a list"},  # Will be ignored, not error
        )

        # Should succeed with empty seeds (lenient normalization)
        normalized = transformer.normalize(raw)
        assert normalized.seeds == []  # Invalid format ignored

    def test_normalize_with_valid_seeds(self) -> None:
        """Test normalization with valid seeds."""
        transformer = Transformer()

        raw = RawEvent(
            source="test",
            timestamp=datetime.now(timezone.utc),
            payload={"seeds": [1.0, 2.0, 3.0]},
        )

        normalized = transformer.normalize(raw)
        assert normalized.seeds == [1.0, 2.0, 3.0]
