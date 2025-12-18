# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Core interfaces and protocols for TradePulse infrastructure.

This module defines the foundational contracts (protocols/ABCs) that
standardize interactions between core subsystems. These interfaces
enable loose coupling, testability, and consistent behavior across
the TradePulse platform.

Contracts defined:
    - DataSource: Data ingestion interface
    - Indicator: Pure indicator computation interface
    - FeatureStore: Feature storage/retrieval interface
    - EventBus: Event pub/sub interface
    - RiskSignal: Risk assessment interface
    - EngineClock: Time source abstraction
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Generic,
    Iterable,
    Mapping,
    Protocol,
    TypeVar,
    runtime_checkable,
)

if TYPE_CHECKING:
    pass

# Type variables for generic interfaces
T = TypeVar("T")
EventT = TypeVar("EventT")
DataT = TypeVar("DataT")
FeatureT = TypeVar("FeatureT")


@dataclass(frozen=True, slots=True)
class DataRecord:
    """Standard data record returned by DataSource implementations.

    Attributes:
        source: Identifier of the data source
        symbol: Trading symbol or asset identifier
        timestamp: Record timestamp (UTC)
        payload: Data payload (OHLCV, tick data, etc.)
        metadata: Additional metadata (quality flags, etc.)
    """

    source: str
    symbol: str
    timestamp: datetime
    payload: Mapping[str, Any]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class DataSource(Protocol[DataT]):
    """Protocol for data source implementations.

    DataSource provides a standardized interface for fetching market data
    from various sources (exchanges, files, databases). Implementations
    should be stateless and support deterministic replay when given the
    same parameters.

    Type Parameters:
        DataT: The type of data records returned by this source
    """

    @property
    def source_id(self) -> str:
        """Unique identifier for this data source."""
        ...

    def fetch(
        self,
        *,
        symbols: Iterable[str],
        start: datetime,
        end: datetime,
        **kwargs: Any,
    ) -> Iterable[DataT]:
        """Fetch data for the specified symbols and time range.

        Args:
            symbols: Trading symbols to fetch
            start: Start of time range (inclusive, UTC)
            end: End of time range (exclusive, UTC)
            **kwargs: Source-specific parameters

        Returns:
            Iterable of data records

        Raises:
            ValidationError: If parameters are invalid
            IntegrityError: If data integrity checks fail
        """
        ...

    def validate_connection(self) -> bool:
        """Check if the data source connection is healthy.

        Returns:
            True if connection is valid, False otherwise
        """
        ...


@dataclass(frozen=True, slots=True)
class IndicatorResult:
    """Result of an indicator computation.

    Attributes:
        name: Indicator name
        value: Computed indicator value
        timestamp: Computation timestamp
        fingerprint: Cache key/fingerprint for the computation
        metadata: Additional metadata (confidence, diagnostics)
    """

    name: str
    value: Any
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    fingerprint: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class Indicator(Protocol):
    """Protocol for indicator implementations.

    Indicators are pure functions that compute analytics from input data.
    Implementations should be deterministic (same inputs → same outputs)
    and support fingerprinting for cache invalidation.
    """

    @property
    def name(self) -> str:
        """Unique name for this indicator."""
        ...

    @property
    def parameters(self) -> Mapping[str, Any]:
        """Current parameters affecting computation."""
        ...

    def compute(
        self,
        data: Any,
        *,
        seed: int | None = None,
        **kwargs: Any,
    ) -> IndicatorResult:
        """Compute the indicator value from input data.

        Args:
            data: Input data (typically numpy array or pandas DataFrame)
            seed: Optional random seed for deterministic RNG behavior
            **kwargs: Additional computation parameters

        Returns:
            IndicatorResult with computed value and metadata

        Raises:
            ValidationError: If input data is invalid
        """
        ...

    def fingerprint(self, data: Any, **kwargs: Any) -> str:
        """Generate a unique fingerprint for cache key generation.

        The fingerprint should change when:
        - Input data changes
        - Indicator parameters change
        - Any other factor affecting output changes

        Args:
            data: Input data
            **kwargs: Computation parameters

        Returns:
            Hex-encoded fingerprint string
        """
        ...


@dataclass(frozen=True, slots=True)
class Feature:
    """A named feature with value and metadata.

    Attributes:
        name: Feature name
        value: Feature value
        timestamp: When feature was computed/stored
        version: Feature schema version
        metadata: Additional metadata
    """

    name: str
    value: Any
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: str = "1.0"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class FeatureStore(Protocol[FeatureT]):
    """Protocol for feature store implementations.

    FeatureStore provides an interface for storing and retrieving computed
    features. Supports both online (real-time) and offline (batch) access
    patterns.

    Type Parameters:
        FeatureT: The type of features stored
    """

    def get(
        self,
        feature_name: str,
        entity_id: str,
        *,
        timestamp: datetime | None = None,
    ) -> FeatureT | None:
        """Retrieve a feature value.

        Args:
            feature_name: Name of the feature
            entity_id: Entity identifier (e.g., symbol)
            timestamp: Point-in-time lookup (None for latest)

        Returns:
            Feature value if found, None otherwise
        """
        ...

    def get_batch(
        self,
        feature_names: Iterable[str],
        entity_ids: Iterable[str],
        *,
        timestamp: datetime | None = None,
    ) -> Mapping[str, Mapping[str, FeatureT | None]]:
        """Retrieve multiple features for multiple entities.

        Args:
            feature_names: Names of features to retrieve
            entity_ids: Entity identifiers
            timestamp: Point-in-time lookup (None for latest)

        Returns:
            Nested mapping: feature_name → entity_id → value
        """
        ...

    def put(
        self,
        feature_name: str,
        entity_id: str,
        value: FeatureT,
        *,
        timestamp: datetime | None = None,
    ) -> None:
        """Store a feature value.

        Args:
            feature_name: Name of the feature
            entity_id: Entity identifier
            value: Feature value to store
            timestamp: Effective timestamp (None for now)
        """
        ...

    def put_batch(
        self,
        features: Iterable[tuple[str, str, FeatureT, datetime | None]],
    ) -> None:
        """Store multiple features atomically.

        Args:
            features: Iterable of (feature_name, entity_id, value, timestamp)
        """
        ...


@dataclass(frozen=True, slots=True)
class Event(Generic[T]):
    """Generic event wrapper for the event bus.

    Attributes:
        event_type: Type/topic of the event
        payload: Event data
        event_id: Unique event identifier
        timestamp: When event was created
        correlation_id: For distributed tracing
        idempotency_key: For exactly-once processing
    """

    event_type: str
    payload: T
    event_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: str | None = None
    idempotency_key: str | None = None


EventHandler = Callable[[Event[Any]], None]


@runtime_checkable
class EventBus(Protocol[EventT]):
    """Protocol for event bus implementations.

    EventBus provides pub/sub semantics for domain events with support
    for correlation IDs, idempotency, and ordered delivery within topics.

    Type Parameters:
        EventT: The type of event payloads
    """

    def publish(
        self,
        event_type: str,
        payload: EventT,
        *,
        event_id: str | None = None,
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> str:
        """Publish an event to the bus.

        Args:
            event_type: Event type/topic
            payload: Event data
            event_id: Optional explicit event ID
            correlation_id: Optional correlation ID for tracing
            idempotency_key: Optional key for exactly-once semantics

        Returns:
            The event ID (generated if not provided)
        """
        ...

    def subscribe(
        self,
        event_type: str,
        handler: EventHandler,
        *,
        group: str | None = None,
    ) -> str:
        """Subscribe to events of a given type.

        Args:
            event_type: Event type/topic to subscribe to
            handler: Callback function to invoke on events
            group: Optional consumer group for load balancing

        Returns:
            Subscription ID for later unsubscription
        """
        ...

    def unsubscribe(self, subscription_id: str) -> bool:
        """Remove a subscription.

        Args:
            subscription_id: ID returned from subscribe()

        Returns:
            True if subscription was found and removed
        """
        ...


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    """Result of a risk assessment.

    Attributes:
        approved: Whether the action is approved
        risk_score: Numeric risk score (0-1, higher = riskier)
        reason: Human-readable reason for decision
        constraints: Any constraints applied to the action
        timestamp: When assessment was made
    """

    approved: bool
    risk_score: float = 0.0
    reason: str | None = None
    constraints: Mapping[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@runtime_checkable
class RiskSignal(Protocol):
    """Protocol for risk signal/assessment implementations.

    RiskSignal evaluates proposed actions and returns risk assessments.
    Implementations should fail-safe (reject on error) and support
    resource budget tracking.
    """

    def assess(
        self,
        action: Mapping[str, Any],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> RiskAssessment:
        """Assess the risk of a proposed action.

        Args:
            action: Description of the proposed action
            context: Additional context (market state, portfolio, etc.)

        Returns:
            RiskAssessment with approval status and details
        """
        ...

    def check_budget(
        self,
        resource: str,
        requested: float,
    ) -> bool:
        """Check if a resource budget allows the requested amount.

        Args:
            resource: Resource identifier (e.g., "latency_ms", "memory_mb")
            requested: Amount being requested

        Returns:
            True if budget allows, False otherwise
        """
        ...


@runtime_checkable
class EngineClock(Protocol):
    """Protocol for time source abstraction.

    EngineClock provides a consistent time interface that can be
    mocked for testing and backtesting scenarios. Supports both
    wall-clock and simulated time.
    """

    def now(self) -> datetime:
        """Get the current time (UTC).

        Returns:
            Current datetime in UTC
        """
        ...

    def sleep(self, seconds: float) -> None:
        """Sleep for the specified duration.

        In simulation mode, this may advance simulated time
        rather than actually sleeping.

        Args:
            seconds: Duration to sleep
        """
        ...

    @property
    def is_simulated(self) -> bool:
        """Check if clock is in simulation mode.

        Returns:
            True if simulated time, False for wall-clock
        """
        ...


class WallClock(EngineClock):
    """Wall-clock implementation of EngineClock.

    Uses actual system time. This is the default implementation
    for production use.
    """

    def now(self) -> datetime:
        """Get current UTC time from system clock."""
        return datetime.now(timezone.utc)

    def sleep(self, seconds: float) -> None:
        """Sleep using time.sleep()."""
        import time

        time.sleep(seconds)

    @property
    def is_simulated(self) -> bool:
        """Wall clock is never simulated."""
        return False


class SimulatedClock(EngineClock):
    """Simulated clock for testing and backtesting.

    Provides deterministic time control for reproducible tests.
    """

    def __init__(self, start_time: datetime | None = None) -> None:
        """Initialize with optional start time.

        Args:
            start_time: Initial simulated time (defaults to epoch)
        """
        self._current = start_time or datetime(1970, 1, 1, tzinfo=timezone.utc)

    def now(self) -> datetime:
        """Get current simulated time."""
        return self._current

    def sleep(self, seconds: float) -> None:
        """Advance simulated time (no actual sleep)."""
        from datetime import timedelta

        self._current = self._current + timedelta(seconds=seconds)

    @property
    def is_simulated(self) -> bool:
        """Simulated clock is always simulated."""
        return True

    def advance(self, seconds: float) -> None:
        """Explicitly advance simulated time.

        Args:
            seconds: Seconds to advance
        """
        self.sleep(seconds)

    def set_time(self, time: datetime) -> None:
        """Set the simulated time to a specific value.

        Args:
            time: New simulated time
        """
        self._current = time


class LifecycleComponent(ABC):
    """Abstract base class for components with lifecycle management.

    Provides start/stop semantics and health checking for
    components that need explicit lifecycle management.
    """

    @abstractmethod
    def start(self) -> None:
        """Start the component.

        Should be idempotent (calling multiple times is safe).
        """

    @abstractmethod
    def stop(self) -> None:
        """Stop the component gracefully.

        Should be idempotent and handle cleanup.
        """

    @abstractmethod
    def is_healthy(self) -> bool:
        """Check if the component is healthy.

        Returns:
            True if component is running and healthy
        """

    @property
    @abstractmethod
    def component_name(self) -> str:
        """Get the component's name for logging/metrics."""


__all__ = [
    # Data types
    "DataRecord",
    "IndicatorResult",
    "Feature",
    "Event",
    "RiskAssessment",
    # Protocols
    "DataSource",
    "Indicator",
    "FeatureStore",
    "EventBus",
    "EventHandler",
    "RiskSignal",
    "EngineClock",
    # Implementations
    "WallClock",
    "SimulatedClock",
    "LifecycleComponent",
]
