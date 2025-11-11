"""Service for regime modulation business logic."""

from __future__ import annotations

import time
from datetime import datetime

from sqlalchemy.orm import Session

from ..config import RegimeSettings
from ..constants import REGIME_CACHE_TTL_SECONDS
from ..errors import ValidationError
from ..logger import get_logger
from ..memory.repository import MemoryRepository
from ..metrics import DB_OPERATION_LATENCY, REGIME_TRANSITIONS, REGIME_UPDATES
from ..modulation.regime import RegimeModulator, RegimeState

logger = get_logger(__name__)


class RegimeCache:
    """Simple TTL cache for latest regime state."""

    def __init__(self, ttl_seconds: float = REGIME_CACHE_TTL_SECONDS) -> None:
        """Initialize the cache.

        Args:
            ttl_seconds: Time-to-live for cached values in seconds
        """
        self._ttl = ttl_seconds
        self._cached_state: RegimeState | None = None
        self._cached_at: float = 0.0

    def get(self) -> RegimeState | None:
        """Get cached regime state if still valid.

        Returns:
            Cached regime state or None if expired
        """
        if self._cached_state is None:
            return None

        if time.monotonic() - self._cached_at > self._ttl:
            self._cached_state = None
            return None

        return self._cached_state

    def set(self, state: RegimeState) -> None:
        """Cache a regime state.

        Args:
            state: Regime state to cache
        """
        self._cached_state = state
        self._cached_at = time.monotonic()

    def invalidate(self) -> None:
        """Clear the cache."""
        self._cached_state = None
        self._cached_at = 0.0


class RegimeService:
    """Service layer for regime modulation operations."""

    def __init__(self, settings: RegimeSettings) -> None:
        """Initialize the regime service.

        Args:
            settings: Regime modulation settings
        """
        self._settings = settings
        self._modulator = RegimeModulator(settings)
        self._cache = RegimeCache()

    def update_regime(
        self, session: Session, feedback: float, volatility: float, as_of: datetime
    ) -> RegimeState:
        """Update market regime based on feedback.

        Args:
            session: Database session
            feedback: Feedback signal value
            volatility: Current market volatility
            as_of: Timestamp for this update

        Returns:
            Updated regime state

        Raises:
            ValidationError: If inputs are invalid
        """
        if volatility < 0:
            raise ValidationError(
                "Volatility must be non-negative", details={"volatility": volatility}
            )

        repository = MemoryRepository(session)

        # Try to get from cache first
        start = time.perf_counter()
        previous_state = self._cache.get()

        if previous_state is None:
            # Cache miss, fetch from database
            previous = repository.latest_regime()
            if previous:
                previous_state = RegimeState(
                    label=previous.label,
                    valence=previous.valence,
                    confidence=previous.confidence,
                    as_of=previous.as_of,
                )
            DB_OPERATION_LATENCY.labels(operation="fetch_regime").observe(
                time.perf_counter() - start
            )

        # Update regime
        updated_state = self._modulator.update(
            previous_state, feedback, volatility, as_of
        )

        # Persist to database
        start = time.perf_counter()
        repository.store_regime(
            updated_state.label,
            updated_state.valence,
            updated_state.confidence,
            updated_state.as_of,
        )
        DB_OPERATION_LATENCY.labels(operation="store_regime").observe(
            time.perf_counter() - start
        )

        # Update cache
        self._cache.set(updated_state)

        # Record metrics
        REGIME_UPDATES.labels(regime=updated_state.label).inc()
        if previous_state and previous_state.label != updated_state.label:
            REGIME_TRANSITIONS.labels(
                from_regime=previous_state.label, to_regime=updated_state.label
            ).inc()

        logger.debug(
            "Updated regime",
            extra={
                "previous_label": previous_state.label if previous_state else None,
                "new_label": updated_state.label,
                "valence": updated_state.valence,
                "confidence": updated_state.confidence,
            },
        )

        return updated_state


__all__ = ["RegimeService", "RegimeCache"]
