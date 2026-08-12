"""Shared fixtures and markers for CoherenceBridge test suite.

Markers:
  @pytest.mark.fast        — <1s, deterministic, no external deps
  @pytest.mark.slow        — Hypothesis property tests, >1s
  @pytest.mark.integration — requires Docker/QuestDB/Kafka
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import numpy as np
import pytest

from coherence_bridge.mock_engine import MockEngine


@pytest.fixture(autouse=True)
def _deterministic_seed() -> None:
    """Fix numpy seed for every test — zero flaky tolerance."""
    np.random.seed(42)


@pytest.fixture
def mock_engine() -> MockEngine:
    """Fresh MockEngine instance."""
    return MockEngine()


@pytest.fixture
def sample_signal(mock_engine: MockEngine) -> dict[str, object]:
    """One valid signal from MockEngine."""
    sig = mock_engine.get_signal("EURUSD")
    assert sig is not None
    return sig


@pytest.fixture
def mock_questdb_writer() -> MagicMock:
    """QuestDB writer mock that accepts write_signal/write_batch."""
    writer = MagicMock()
    writer.write_signal = MagicMock()
    writer.write_batch = MagicMock()
    return writer


@pytest.fixture
def geosync_available() -> bool:
    """Check if GeoSync physics kernel is importable."""
    geosync_path = os.getenv(
        "GEOSYNC_PATH",
        "/home/neuro7/Desktop/Торгова систа легенда/GeoSync-main (4)/GeoSync-main",
    )
    if geosync_path not in sys.path:
        sys.path.insert(0, geosync_path)
    try:
        from core.indicators.kuramoto_ricci_composite import (  # noqa: F401
            GeoSyncCompositeEngine,
        )

        return True
    except ImportError:
        return False
