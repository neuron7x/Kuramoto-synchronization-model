"""Strategy execution engine with modular contracts and risk-aware routing."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import (
    Any,
    Callable,
    Iterable,
    Mapping,
    MutableMapping,
    Protocol,
    Sequence,
)

from core.events.models import SignalDirection


def _freeze_mapping(mapping: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """Return an immutable view over ``mapping``."""

    if mapping is None:
        return MappingProxyType({})
    if isinstance(mapping, MappingProxyType):
        return mapping
    return MappingProxyType(dict(mapping))


def _normalize_contract_value(value: Any) -> Any:
    """Recursively convert dataclasses and mapping proxies into plain values."""

    if is_dataclass(value):
        return _dataclass_to_mapping(value)
    if isinstance(value, Mapping):
        return {k: _normalize_contract_value(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return tuple(_normalize_contract_value(v) for v in value)
    if isinstance(value, list):
        return [_normalize_contract_value(v) for v in value]
    if isinstance(value, set):
        return {_normalize_contract_value(v) for v in value}
    if isinstance(value, frozenset):
        return frozenset(_normalize_contract_value(v) for v in value)
    return value


def _dataclass_to_mapping(instance: Any) -> Mapping[str, Any]:
    """Return a mapping representation for a dataclass ``instance``."""

    materialised: dict[str, Any] = {}
    for field_info in fields(instance):
        materialised[field_info.name] = _normalize_contract_value(
            getattr(instance, field_info.name)
        )
    return materialised


def _coerce_contract_payload(payload: Any) -> Mapping[str, Any]:
    """Convert ``payload`` into a mapping suitable for contract validation."""

    if isinstance(payload, Mapping):
        return payload
    if is_dataclass(payload):
        return _dataclass_to_mapping(payload)
    raise TypeError(
        "Strategy module outputs must be mapping-like or dataclass instances to"
        " satisfy IO contract validation"
    )


class StrategyEngineError(RuntimeError):
    """Base exception for the strategy engine."""


class InvalidModeTransition(StrategyEngineError):
    """Raised when an illegal mode transition is attempted."""


class StrategyEngineMode(str, Enum):
    """Operational modes supported by :class:`StrategyEngine`."""

    LIVE = "live"
    PAPER = "paper"
    PAUSED = "paused"


@dataclass(frozen=True, slots=True)
class IOContract:
    """Declarative contract describing module inputs or outputs."""

    required: Mapping[str, type | tuple[type, ...] | None] = field(default_factory=dict)
    optional: Mapping[str, type | tuple[type, ...] | None] = field(default_factory=dict)
    description: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "required", MappingProxyType(dict(self.required)))
        object.__setattr__(self, "optional", MappingProxyType(dict(self.optional)))

    def validate(self, payload: Mapping[str, Any], *, contract_name: str) -> None:
        """Validate ``payload`` against the declared contract."""

        missing = [field for field in self.required if field not in payload]
        if missing:
            joined = ", ".join(sorted(missing))
            raise ValueError(
                f"Missing required inputs for {contract_name!r}: [{joined}]"
            )

        for field_name, expected in self.required.items():
            if expected is None:
                continue
            self._assert_type(payload[field_name], expected, field_name, contract_name)

        for field_name, expected in self.optional.items():
            if field_name not in payload or expected is None:
                continue
            self._assert_type(payload[field_name], expected, field_name, contract_name)

    @staticmethod
    def _assert_type(
        value: Any,
        expected: type | tuple[type, ...],
        field_name: str,
        contract_name: str,
    ) -> None:
        types: Sequence[type]
        if isinstance(expected, tuple):
            types = expected
        else:
            types = (expected,)
        if not any(isinstance(value, candidate) for candidate in types):
            type_names = ", ".join(tp.__name__ for tp in types)
            raise TypeError(
                f"Field '{field_name}' for {contract_name!r} expected type(s)"
                f" [{type_names}] but received {type(value).__name__}"
            )


@dataclass(frozen=True, slots=True)
class StrategyContext:
    """Runtime context passed to strategy modules."""

    timestamp: datetime
    data: Mapping[str, Any]
    metadata: Mapping[str, Any] = field(default_factory=dict)
    mode: StrategyEngineMode = StrategyEngineMode.PAPER

    def __post_init__(self) -> None:
        timestamp = self.timestamp
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        object.__setattr__(self, "timestamp", timestamp)
        object.__setattr__(self, "data", _freeze_mapping(self.data))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class StrategySignal:
    """Structured representation of a trading signal."""

    signal_id: str
    symbol: str
    direction: SignalDirection
    strength: float
    confidence: float = 1.0
    issued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class StrategyCancel:
    """Cancellation request emitted by a strategy module."""

    signal_id: str
    reason: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


class RiskAdviceLevel(str, Enum):
    """Severity levels for risk guidance events."""

    INFO = "info"
    WARN = "warn"
    BLOCK = "block"


@dataclass(frozen=True, slots=True)
class RiskAdvice:
    """Guidance generated by the risk layer for a signal or strategy."""

    level: RiskAdviceLevel
    message: str
    signal_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class StrategyEngineEvent:
    """Envelope for events produced by strategy modules."""

    type: "StrategyEventType"
    module: str
    payload: StrategySignal | StrategyCancel | RiskAdvice


class StrategyEventType(str, Enum):
    """Supported event types produced by strategy modules."""

    SIGNAL = "signal"
    CANCEL = "cancel"
    RISK_ADVICE = "risk-advice"


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    """Outcome of validating a signal against the risk policy."""

    approved: bool
    reason: str | None = None
    adjustments: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "adjustments", _freeze_mapping(self.adjustments))

    def apply(self, signal: StrategySignal) -> StrategySignal:
        """Return a copy of ``signal`` after applying recommended adjustments."""

        if not self.adjustments:
            return signal

        updated = signal
        if "strength" in self.adjustments:
            updated = replace(updated, strength=float(self.adjustments["strength"]))
        if "confidence" in self.adjustments:
            updated = replace(updated, confidence=float(self.adjustments["confidence"]))
        if "metadata" in self.adjustments:
            merged: MutableMapping[str, Any] = dict(updated.metadata)
            metadata_update = self.adjustments["metadata"]
            if not isinstance(metadata_update, Mapping):
                raise TypeError(
                    "Risk adjustments 'metadata' must be a mapping, got"
                    f" {type(metadata_update).__name__}"
                )
            merged.update(metadata_update)
            updated = replace(updated, metadata=_freeze_mapping(merged))
        return updated


class RiskPolicy(Protocol):
    """Contract for evaluating signals prior to OMS routing."""

    def assess(
        self, signal: StrategySignal, *, mode: StrategyEngineMode
    ) -> RiskAssessment:
        """Return the risk assessment for ``signal``."""


class AcceptAllRiskPolicy:
    """Default risk policy that approves every signal."""

    def assess(
        self, signal: StrategySignal, *, mode: StrategyEngineMode
    ) -> RiskAssessment:
        return RiskAssessment(approved=True)


class StrategyModule(Protocol):
    """Strategy building block exposing explicit IO contracts."""

    name: str
    input_contract: IOContract
    output_contract: IOContract

    def process(
        self, context: StrategyContext
    ) -> Iterable[StrategyEngineEvent] | StrategyEngineEvent | None:
        """Produce zero or more :class:`StrategyEngineEvent` objects."""


SignalRouter = Callable[[StrategySignal, RiskAssessment], None]
CancelRouter = Callable[[StrategyCancel], None]
RiskAdviceSink = Callable[[RiskAdvice], None]
EventListener = Callable[[StrategyEngineEvent], None]


class StrategyEngine:
    """Coordinate strategy modules, risk validation, and event routing."""

    _ALLOWED_TRANSITIONS: Mapping[StrategyEngineMode, set[StrategyEngineMode]] = {
        StrategyEngineMode.PAPER: {
            StrategyEngineMode.LIVE,
            StrategyEngineMode.PAUSED,
            StrategyEngineMode.PAPER,
        },
        StrategyEngineMode.LIVE: {
            StrategyEngineMode.PAPER,
            StrategyEngineMode.PAUSED,
            StrategyEngineMode.LIVE,
        },
        StrategyEngineMode.PAUSED: {
            StrategyEngineMode.PAPER,
            StrategyEngineMode.LIVE,
            StrategyEngineMode.PAUSED,
        },
    }

    def __init__(
        self,
        *,
        risk_policy: RiskPolicy | None = None,
        signal_router: SignalRouter | None = None,
        cancel_router: CancelRouter | None = None,
        risk_advice_sink: RiskAdviceSink | None = None,
        modules: Iterable[StrategyModule] | None = None,
    ) -> None:
        self._risk_policy = risk_policy or AcceptAllRiskPolicy()
        self._signal_router = signal_router or (lambda signal, assessment: None)
        self._cancel_router = cancel_router or (lambda cancel: None)
        self._risk_advice_sink = risk_advice_sink or (lambda advice: None)
        self._mode = StrategyEngineMode.PAPER
        self._last_active_mode = StrategyEngineMode.PAPER
        self._modules: dict[str, StrategyModule] = {}
        self._listeners: dict[StrategyEventType, list[EventListener]] = {
            StrategyEventType.SIGNAL: [],
            StrategyEventType.CANCEL: [],
            StrategyEventType.RISK_ADVICE: [],
        }
        if modules:
            for module in modules:
                self.register_module(module)

    @property
    def mode(self) -> StrategyEngineMode:
        return self._mode

    @property
    def modules(self) -> Mapping[str, StrategyModule]:
        return MappingProxyType(dict(self._modules))

    def register_module(self, module: StrategyModule) -> None:
        """Register a strategy module ensuring unique names."""

        if module.name in self._modules:
            raise ValueError(f"Strategy module '{module.name}' already registered")
        self._modules[module.name] = module

    def unregister_module(self, name: str) -> None:
        """Remove a previously registered module."""

        self._modules.pop(name, None)

    def subscribe(self, event_type: StrategyEventType, listener: EventListener) -> None:
        """Register a listener invoked for emitted events."""

        self._listeners[event_type].append(listener)

    def set_mode(self, mode: StrategyEngineMode) -> None:
        """Transition the engine into ``mode`` if permitted."""

        if mode not in self._ALLOWED_TRANSITIONS[self._mode]:
            raise InvalidModeTransition(
                f"Cannot transition from {self._mode} to {mode}"
            )
        self._mode = mode
        if mode is not StrategyEngineMode.PAUSED:
            self._last_active_mode = mode

    def pause(self) -> None:
        """Enter the paused state regardless of the active mode."""

        self.set_mode(StrategyEngineMode.PAUSED)

    def resume(self) -> None:
        """Resume the engine using the last active non-paused mode."""

        if self._mode is not StrategyEngineMode.PAUSED:
            raise InvalidModeTransition("Engine is not paused")
        self.set_mode(self._last_active_mode)

    def process(self, context: StrategyContext) -> tuple[StrategyEngineEvent, ...]:
        """Process ``context`` through all registered modules."""

        if self._mode is StrategyEngineMode.PAUSED:
            return ()

        if context.mode is not self._mode:
            context = replace(context, mode=self._mode)

        emitted: list[StrategyEngineEvent] = []
        for module in self._modules.values():
            module.input_contract.validate(context.data, contract_name=module.name)
            raw_events = module.process(context)
            if raw_events is None:
                continue
            events: Iterable[StrategyEngineEvent]
            if isinstance(raw_events, StrategyEngineEvent):
                events = (raw_events,)
            else:
                events = tuple(raw_events)
            for event in events:
                processed = self._handle_event(event)
                emitted.extend(processed)
        return tuple(emitted)

    # ---------------------------------------------------------------------
    # Internal helpers

    def _handle_event(
        self, event: StrategyEngineEvent
    ) -> tuple[StrategyEngineEvent, ...]:
        self._validate_event(event)
        self._validate_output_contract(event)
        if event.type is StrategyEventType.SIGNAL:
            return self._handle_signal(event)
        if event.type is StrategyEventType.CANCEL:
            self._notify_listeners(event)
            self._cancel_router(event.payload)  # type: ignore[arg-type]
            return (event,)
        if event.type is StrategyEventType.RISK_ADVICE:
            self._notify_listeners(event)
            self._risk_advice_sink(event.payload)  # type: ignore[arg-type]
            return (event,)
        return ()

    def _handle_signal(
        self, event: StrategyEngineEvent
    ) -> tuple[StrategyEngineEvent, ...]:
        signal_payload = event.payload
        if not isinstance(signal_payload, StrategySignal):
            msg = "Signal events must carry StrategySignal payloads"
            raise TypeError(msg)
        signal = signal_payload
        assessment = self._risk_policy.assess(signal, mode=self._mode)
        adjusted_signal = assessment.apply(signal)
        dispatched: list[StrategyEngineEvent] = []

        if not assessment.approved:
            advice = RiskAdvice(
                level=RiskAdviceLevel.BLOCK,
                message=assessment.reason or "Signal blocked by risk policy",
                signal_id=signal.signal_id,
                metadata=assessment.adjustments,
            )
            advice_event = StrategyEngineEvent(
                type=StrategyEventType.RISK_ADVICE,
                module=event.module,
                payload=advice,
            )
            self._notify_listeners(advice_event)
            self._risk_advice_sink(advice)
            dispatched.append(advice_event)
            return tuple(dispatched)

        adjusted_event = StrategyEngineEvent(
            type=StrategyEventType.SIGNAL,
            module=event.module,
            payload=adjusted_signal,
        )
        self._notify_listeners(adjusted_event)
        self._signal_router(adjusted_signal, assessment)
        dispatched.append(adjusted_event)

        if assessment.adjustments:
            advice = RiskAdvice(
                level=RiskAdviceLevel.WARN,
                message=assessment.reason or "Signal adjusted by risk policy",
                signal_id=signal.signal_id,
                metadata=assessment.adjustments,
            )
            advice_event = StrategyEngineEvent(
                type=StrategyEventType.RISK_ADVICE,
                module=event.module,
                payload=advice,
            )
            self._notify_listeners(advice_event)
            self._risk_advice_sink(advice)
            dispatched.append(advice_event)

        return tuple(dispatched)

    def _validate_event(self, event: StrategyEngineEvent) -> None:
        if event.type is StrategyEventType.SIGNAL and not isinstance(
            event.payload, StrategySignal
        ):
            raise TypeError("Signal events must carry StrategySignal payloads")
        if event.type is StrategyEventType.CANCEL and not isinstance(
            event.payload, StrategyCancel
        ):
            raise TypeError("Cancel events must carry StrategyCancel payloads")
        if event.type is StrategyEventType.RISK_ADVICE and not isinstance(
            event.payload, RiskAdvice
        ):
            raise TypeError("Risk-advice events must carry RiskAdvice payloads")

    def _validate_output_contract(self, event: StrategyEngineEvent) -> None:
        module = self._modules.get(event.module)
        if module is None:
            raise StrategyEngineError(
                f"Event references unknown strategy module {event.module!r}"
            )
        contract = module.output_contract
        if not contract.required and not contract.optional:
            return
        payload_mapping = _coerce_contract_payload(event.payload)
        contract.validate(
            payload_mapping,
            contract_name=f"{module.name}:{event.type.value}",
        )

    def _notify_listeners(self, event: StrategyEngineEvent) -> None:
        for listener in self._listeners[event.type]:
            listener(event)


__all__ = [
    "StrategyEngine",
    "StrategyEngineMode",
    "StrategyEngineError",
    "InvalidModeTransition",
    "StrategyModule",
    "StrategyContext",
    "StrategySignal",
    "StrategyCancel",
    "StrategyEngineEvent",
    "StrategyEventType",
    "RiskAdvice",
    "RiskAdviceLevel",
    "RiskAssessment",
    "RiskPolicy",
    "AcceptAllRiskPolicy",
    "IOContract",
]
