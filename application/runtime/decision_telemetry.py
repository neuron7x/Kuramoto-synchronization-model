# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Semantic telemetry helpers for control-gate decisions."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import time
from typing import Any, Iterable, Mapping, TypedDict

try:  # pragma: no cover - optional dependency
    from opentelemetry.trace import get_current_span
except Exception:  # pragma: no cover - tracing is optional
    get_current_span = None  # type: ignore[assignment]

try:  # pragma: no cover - optional dependency for metrics
    from prometheus_client import Counter, Gauge, Histogram
except Exception:  # pragma: no cover - metrics are optional
    Counter = None  # type: ignore[assignment]
    Gauge = None  # type: ignore[assignment]
    Histogram = None  # type: ignore[assignment]

from core.utils.metrics import get_metrics_collector

LOGGER = logging.getLogger("geosync.control_gates")
GATE_PIPELINE_VERSION = "gate_pipeline.v1"
_PROXY_RISK_KEYWORDS = ("risk", "stress", "drawdown")
_SEROTONIN_MISSING_FLAG = "serotonin_missing"
_THERMO_MISSING_FLAG = "thermo_missing"
_SEROTONIN_PROXY_FLAGS = (_SEROTONIN_MISSING_FLAG, "stress_proxy", "drawdown_proxy")
_THERMO_PROXY_FLAGS = ("thermo_free_energy_proxy", _THERMO_MISSING_FLAG)
_CONTROL_GATE_THROTTLE_BUCKETS = (0, 10, 50, 100, 250, 500, 1000, 2500, 5000, float("inf"))
_SEROTONIN_KEY = "serotonin"
_THERMO_KEY = "thermo"


class DecisionTelemetryEvent(TypedDict):
    ts_unix_ms: int
    decision: str
    position_multiplier: float
    throttle_ms: int
    reasons: list[str]
    controller_states: dict[str, object]
    proxies: dict[str, object]
    inputs_summary: dict[str, object]
    config_fingerprint: str
    trace_id: str | None
    version: str


_METRICS_COLLECTOR = get_metrics_collector()
_REGISTRY = getattr(_METRICS_COLLECTOR, "registry", None) if _METRICS_COLLECTOR else None

CONTROL_GATE_DECISIONS_TOTAL = (
    Counter(
        "control_gate_decisions_total",
        "Total control-gate decisions emitted",
        ["decision"],
        registry=_REGISTRY,
    )
    if Counter is not None
    else None
)
CONTROL_GATE_REASON_TOTAL = (
    Counter(
        "control_gate_reason_total",
        "Total control-gate reasons emitted",
        ["reason"],
        registry=_REGISTRY,
    )
    if Counter is not None
    else None
)
CONTROL_GATE_POSITION_MULTIPLIER = (
    Gauge(
        "control_gate_position_multiplier",
        "Latest control-gate position multiplier",
        registry=_REGISTRY,
    )
    if Gauge is not None
    else None
)
CONTROL_GATE_THROTTLE_MS = (
    Histogram(
        "control_gate_throttle_ms",
        "Observed throttle durations in milliseconds",
        registry=_REGISTRY,
        buckets=_CONTROL_GATE_THROTTLE_BUCKETS,
    )
    if Histogram is not None
    else None
)


def _safe(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (list, tuple, set)):
        return [_safe(item) for item in obj]
    if isinstance(obj, Mapping):
        return {str(key): _safe(value) for key, value in obj.items()}
    if dataclasses.is_dataclass(obj):
        return {str(k): _safe(v) for k, v in dataclasses.asdict(obj).items()}
    if hasattr(obj, "model_dump"):
        try:
            dumped = obj.model_dump()
        except Exception:
            dumped = str(obj)
        return _safe(dumped)
    if hasattr(obj, "__dict__"):
        return {str(k): _safe(v) for k, v in vars(obj).items()}
    return str(obj)


def _sort_mapping(obj: Any) -> Any:
    if isinstance(obj, Mapping):
        return {k: _sort_mapping(obj[k]) for k in sorted(obj)}
    if isinstance(obj, list):
        return [_sort_mapping(item) for item in obj]
    return obj


def fingerprint_config(effective_config: Any) -> str:
    """Generate a stable fingerprint for an effective configuration."""

    safe_repr = _sort_mapping(_safe(effective_config))
    payload = json.dumps(safe_repr, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _resolve_trace_id() -> str | None:
    if get_current_span is None:
        return None
    try:  # pragma: no cover - defensive guard
        span = get_current_span()
        context = span.get_span_context() if span else None
    except Exception:
        return None
    if not context:
        return None
    trace_id = getattr(context, "trace_id", 0)
    if not trace_id:
        return None
    return f"{trace_id:032x}"


def _sanitize_inputs(signals: Mapping[str, object]) -> dict[str, object]:
    sanitized: dict[str, object] = {}
    for key, value in signals.items():
        key_lower = str(key).lower()
        if any(secret in key_lower for secret in ("token", "secret", "password", "cred", "auth")):
            continue
        sanitized[str(key)] = _safe(value)
    return sanitized


def _proxy_flags(meta: Mapping[str, object] | None) -> list[str]:
    if not meta:
        return []
    flags = meta.get("proxy_flags")
    if isinstance(flags, (list, tuple, set)):
        return sorted({str(flag) for flag in flags if flag})
    return []


def build_decision_event(
    *,
    gate: Any,
    telemetry: Mapping[str, object],
    effective_config: Any,
    signals: Mapping[str, object],
    trace_id: str | None = None,
) -> DecisionTelemetryEvent:
    reasons = list(getattr(gate, "reasons", []))
    decision_attr = getattr(gate, "decision", None)
    decision_value = getattr(decision_attr, "value", None) or str(decision_attr or "UNKNOWN")
    if decision_value in ("THROTTLE", "DENY") and not reasons:
        raise ValueError(f"reasons must be populated for decision={decision_value}")

    controller_states = {
        _SEROTONIN_KEY: _safe(telemetry.get(_SEROTONIN_KEY, {})),
        _THERMO_KEY: _safe(telemetry.get(_THERMO_KEY, {})),
    }
    proxy_flags = _proxy_flags(getattr(gate, "meta", None))
    proxies = {
        "missing_metrics": any("missing" in flag for flag in proxy_flags),
        "proxy_energy": any("thermo" in flag or "energy" in flag for flag in proxy_flags),
        "proxy_risk": any(
            keyword in flag for flag in proxy_flags for keyword in _PROXY_RISK_KEYWORDS
        ),
        "flags": proxy_flags,
    }
    event: DecisionTelemetryEvent = {
        "ts_unix_ms": int(time.time() * 1000),
        "decision": decision_value,
        "position_multiplier": float(getattr(gate, "position_multiplier", 0.0)),
        "throttle_ms": int(getattr(gate, "throttle_ms", 0)),
        "reasons": reasons,
        "controller_states": controller_states,
        "proxies": proxies,
        "inputs_summary": _sanitize_inputs(signals),
        "config_fingerprint": fingerprint_config(effective_config),
        "trace_id": trace_id or _resolve_trace_id(),
        "version": GATE_PIPELINE_VERSION,
    }
    return event


def to_json_line(event: DecisionTelemetryEvent) -> str:
    """Render a telemetry event as a JSON line."""

    return json.dumps(event, separators=(",", ":"), sort_keys=True)


def record_decision_metrics(event: DecisionTelemetryEvent) -> None:
    if CONTROL_GATE_DECISIONS_TOTAL is not None:
        CONTROL_GATE_DECISIONS_TOTAL.labels(decision=event["decision"]).inc()
    if CONTROL_GATE_REASON_TOTAL is not None and event.get("reasons"):
        for reason in event["reasons"]:
            CONTROL_GATE_REASON_TOTAL.labels(reason=reason).inc()
    if CONTROL_GATE_POSITION_MULTIPLIER is not None:
        CONTROL_GATE_POSITION_MULTIPLIER.set(float(event["position_multiplier"]))
    if CONTROL_GATE_THROTTLE_MS is not None:
        CONTROL_GATE_THROTTLE_MS.observe(float(event.get("throttle_ms", 0)))


def emit_decision_event(
    event: DecisionTelemetryEvent,
    *,
    logger: logging.Logger | None = None,
) -> None:
    record_decision_metrics(event)
    active_logger = logger or LOGGER
    try:
        active_logger.info("DECISION_EVENT %s", to_json_line(event))
    except Exception:
        active_logger.exception("Failed to emit decision telemetry")


def get_controller_health(
    controllers: Mapping[str, Any],
    *,
    proxy_flags: Iterable[str] | None = None,
    telemetry: Mapping[str, object] | None = None,
) -> dict[str, object]:
    flags = set(proxy_flags or [])
    telemetry = telemetry or {}

    def _status_for_serotonin(ctrl: Any) -> dict[str, object]:
        if ctrl is None:
            return {
                "status": "missing",
                "cooldown": None,
                "last_update": None,
                "notes": [_SEROTONIN_MISSING_FLAG],
            }
        notes: list[str] = []
        cooldown = getattr(ctrl, "cooldown", None) or getattr(ctrl, "cooldown_s", None)
        last_update = getattr(ctrl, "last_update", None)
        if flags & set(_SEROTONIN_PROXY_FLAGS):
            notes.append("proxy_inputs_active")
        metrics_snapshot = (
            telemetry.get(_SEROTONIN_KEY, {}).get("metrics", {})
            if isinstance(telemetry, Mapping)
            else {}
        )
        if metrics_snapshot and metrics_snapshot.get("cooldown_s", 0) and not cooldown:
            cooldown = metrics_snapshot.get("cooldown_s")
        status = "degraded" if notes else "ok"
        return {
            "status": status,
            "cooldown": _safe(cooldown),
            "last_update": _safe(last_update),
            "notes": notes,
        }

    def _status_for_thermo(ctrl: Any) -> dict[str, object]:
        if ctrl is None:
            return {
                "status": "missing",
                "free_energy": None,
                "budget": None,
                "notes": [_THERMO_MISSING_FLAG],
            }
        notes: list[str] = []
        free_energy = getattr(ctrl, "previous_F", None)
        budget = getattr(ctrl, "baseline_F", None)
        if getattr(ctrl, "circuit_breaker_active", False):
            notes.append("circuit_breaker_active")
        if flags & set(_THERMO_PROXY_FLAGS):
            notes.append("proxy_inputs_active")
        status = "degraded" if notes else "ok"
        return {
            "status": status,
            "free_energy": _safe(free_energy),
            "budget": _safe(budget),
            "notes": notes,
        }

    serotonin_state = _status_for_serotonin(controllers.get(_SEROTONIN_KEY))
    thermo_state = _status_for_thermo(controllers.get(_THERMO_KEY))

    overall_notes: list[str] = []
    overall_status = "ok"
    for name, state in ((_SEROTONIN_KEY, serotonin_state), (_THERMO_KEY, thermo_state)):
        if state["status"] == "missing":
            overall_status = "missing"
            overall_notes.append(f"{name}_missing")
        elif state["status"] == "degraded" and overall_status == "ok":
            overall_status = "degraded"
            overall_notes.append(f"{name}_degraded")

    return {
        "serotonin": serotonin_state,
        "thermo": thermo_state,
        "overall": {"status": overall_status, "reasons": overall_notes},
    }


__all__ = [
    "DecisionTelemetryEvent",
    "GATE_PIPELINE_VERSION",
    "build_decision_event",
    "emit_decision_event",
    "fingerprint_config",
    "get_controller_health",
    "to_json_line",
]
