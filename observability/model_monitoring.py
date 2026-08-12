# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Comprehensive observability tooling for production model deployments."""

from __future__ import annotations

import logging
import math
import statistics
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import (
    Callable,
    Deque,
    Dict,
    Iterable,
    Iterator,
    Mapping,
    MutableMapping,
    Sequence,
)

from core.compat import utc_now

try:  # pragma: no cover - optional dependency may not be available
    import psutil

    _PSUTIL_AVAILABLE = True
except Exception:  # pragma: no cover - psutil is optional at runtime
    psutil = None
    _PSUTIL_AVAILABLE = False

from core.utils.metrics import get_metrics_collector

from .incidents import IncidentManager, IncidentRecord
from .tracing import pipeline_span

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class InferenceContext:
    """Mutable context returned to callers during traced inference."""

    status: str = "success"
    span_attributes: Dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class QualityConfidenceInterval:
    """Summary describing the distribution of a quality metric."""

    metric: str
    mean: float
    lower: float
    upper: float
    confidence_level: float
    sample_size: int
    stddev: float
    timestamp: datetime = field(default_factory=lambda: utc_now())

    @property
    def width(self) -> float:
        """Return the width of the confidence interval."""

        return float(self.upper - self.lower)


@dataclass(slots=True)
class QualityBaseline:
    """Guardrail describing the acceptable behaviour of a quality metric."""

    metric: str
    target: float
    tolerance: float
    min_samples: int


@dataclass(slots=True)
class DegradationSignal:
    """Structured record describing an emitted degradation event."""

    metric: str
    observed_value: float
    expected_value: float | None
    severity: float
    reason: str
    timestamp: datetime = field(default_factory=lambda: utc_now())
    incident: IncidentRecord | None = None


@dataclass(slots=True)
class EventLabel:
    """Label applied to noteworthy operational events."""

    name: str
    tags: Mapping[str, object] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: utc_now())


@dataclass(slots=True)
class ResourceSnapshot:
    """Point-in-time resource utilisation view for serving workloads."""

    cpu_percent: float
    memory_percent: float
    memory_bytes: float
    gpu_percent: float | None = None
    saturation: float | None = None
    cache_name: str | None = None
    cache_hit_ratio: float | None = None
    cache_entries: float | None = None
    cache_evictions: int | None = None
    timestamp: datetime = field(default_factory=lambda: utc_now())


@dataclass(slots=True)
class PostmortemTemplate:
    """Opinionated template used for incident postmortems."""

    incident_id: str
    summary: str
    started_at: datetime
    detected_by: str
    severity: str
    timeline: Sequence[EventLabel]
    contributing_metrics: Mapping[str, object]
    remediation_hypotheses: Sequence[str] = ()
    guardrails: Sequence[str] = ()

    def render(self) -> str:
        """Render the template using a Markdown-friendly format."""

        lines: list[str] = []
        lines.append(f"# Incident {self.incident_id}")
        lines.append("")
        lines.append("## Summary")
        lines.append(self.summary)
        lines.append("")
        lines.append("## Detection")
        lines.append(f"- Detected by: {self.detected_by}")
        lines.append(f"- Severity: {self.severity}")
        lines.append(f"- Started at: {self.started_at.isoformat()}")
        lines.append("")
        lines.append("## Contributing metrics")
        for key, value in sorted(self.contributing_metrics.items()):
            lines.append(f"- {key}: {value}")
        lines.append("")
        lines.append("## Timeline")
        for label in self.timeline:
            tag_repr = ", ".join(f"{name}={value}" for name, value in sorted(label.tags.items()))
            payload = f" – {tag_repr}" if tag_repr else ""
            lines.append(f"- {label.timestamp.isoformat()} – {label.name}{payload}")
        lines.append("")
        if self.remediation_hypotheses:
            lines.append("## Remediation hypotheses")
            for entry in self.remediation_hypotheses:
                lines.append(f"- {entry}")
            lines.append("")
        if self.guardrails:
            lines.append("## Guardrails")
            for entry in self.guardrails:
                lines.append(f"- {entry}")
            lines.append("")
        return "\n".join(lines)


@dataclass(slots=True)
class MetricSeries:
    """Fixed-size window retaining recent metric samples."""

    name: str
    maxlen: int
    _samples: Deque[tuple[float, float]] = field(default_factory=deque)

    def append(self, timestamp: float, value: float) -> None:
        self._samples.append((float(timestamp), float(value)))
        if len(self._samples) > self.maxlen:
            self._samples.popleft()

    def values(self, window: int | None = None) -> list[float]:
        data = self.tail(window)
        return [value for _, value in data]

    def tail(self, window: int | None = None) -> list[tuple[float, float]]:
        if window is None or window <= 0:
            return list(self._samples)
        return list(self._samples)[-window:]


@dataclass(slots=True)
class ModelObservabilityConfig:
    """Configuration bundle for :class:`ModelObservabilityOrchestrator`."""

    model_name: str
    environment: str = "production"
    latency_sla_ms: float | None = None
    error_rate_threshold: float | None = None
    max_requests_per_second: float | None = None
    throughput_window_seconds: float = 60.0
    metric_history_size: int = 512
    quality_window: int = 256
    quality_min_samples: int = 5
    confidence_level: float = 0.95
    triage_on_degradation: bool = True
    incident_severity: str = "major"
    incident_root: str | Path | None = None
    degradation_cooldown_seconds: float = 300.0

    def __post_init__(self) -> None:
        if self.throughput_window_seconds <= 0:
            raise ValueError("throughput_window_seconds must be positive")
        if self.metric_history_size <= 0:
            raise ValueError("metric_history_size must be positive")
        if self.quality_window <= 0:
            raise ValueError("quality_window must be positive")
        if not (0.0 < self.confidence_level < 1.0):
            raise ValueError("confidence_level must be within (0, 1)")
        if self.quality_min_samples <= 0:
            raise ValueError("quality_min_samples must be positive")
        if self.degradation_cooldown_seconds < 0:
            raise ValueError("degradation_cooldown_seconds cannot be negative")


class ModelObservabilityOrchestrator:
    """High-level orchestrator that wires tracing, metrics, and triage together."""

    def __init__(
        self,
        config: ModelObservabilityConfig,
        *,
        incident_manager: IncidentManager | None = None,
        perf_counter: Callable[[], float] | None = None,
        monotonic: Callable[[], float] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._metrics = get_metrics_collector()
        self._perf_counter = perf_counter or time.perf_counter
        self._monotonic = monotonic or time.monotonic
        self._now = now or (lambda: utc_now())

        if incident_manager is not None:
            self._incident_manager = incident_manager
        else:
            root = Path(config.incident_root) if config.incident_root else None
            self._incident_manager = IncidentManager(root)

        self._series: Dict[str, MetricSeries] = {}
        self._quality_samples: MutableMapping[str, Deque[float]] = defaultdict(
            lambda: deque(maxlen=config.quality_window)
        )
        self._quality_baselines: Dict[str, QualityBaseline] = {}
        self._quality_intervals: Dict[str, QualityConfidenceInterval] = {}
        self._inference_events: Deque[tuple[float, bool]] = deque()
        self._events: Deque[EventLabel] = deque(maxlen=1024)
        self._degradations: Deque[DegradationSignal] = deque(maxlen=256)
        self._last_degradation_by_metric: Dict[str, float] = {}
        self._incident_library: Dict[str, IncidentRecord] = {}
        self._last_resource_snapshot: ResourceSnapshot | None = None

        self._process = psutil.Process() if _PSUTIL_AVAILABLE else None
        if self._process is not None:  # pragma: no cover - defensive priming
            try:
                self._process.cpu_percent(interval=None)
            except Exception:
                LOGGER.debug("Failed to prime psutil process counters", exc_info=True)

        # Pre-register core series to simplify downstream logic.
        self._get_series("latency_seconds")
        self._get_series("throughput_per_second")
        self._get_series("error_ratio")

    @contextmanager
    def trace_inference(
        self, request_id: str, *, attributes: Mapping[str, object] | None = None
    ) -> Iterator[InferenceContext]:
        """Trace an inference request, emitting metrics and latency statistics."""

        ctx = InferenceContext()
        start = self._perf_counter()

        span_attributes: Dict[str, object] = {
            "model.name": self._config.model_name,
            "deployment.environment": self._config.environment,
            "request.id": request_id,
        }
        if attributes:
            span_attributes.update({str(key): value for key, value in attributes.items()})

        self.label_event("inference.start", {"request_id": request_id})
        span = pipeline_span(f"model.{self._config.model_name}.inference", **span_attributes)
        with span as active_span:
            error: BaseException | None = None
            try:
                yield ctx
            except Exception as exc:  # pragma: no cover - surfaced via tests
                ctx.status = "error"
                error = exc
                raise
            finally:
                if ctx.span_attributes and active_span is not None:
                    try:
                        active_span.set_attributes(ctx.span_attributes)
                    except Exception:  # pragma: no cover - tracing defensive path
                        LOGGER.debug("Failed to set span attributes", exc_info=True)

                duration = self._perf_counter() - start
                status = ctx.status.strip().lower() if ctx.status else "success"
                if error is not None:
                    status = "error"
                success = status == "success"
                self._finalise_inference(
                    duration=duration,
                    success=success,
                    status=status,
                )
                self.label_event(
                    "inference.completed",
                    {
                        "request_id": request_id,
                        "status": status,
                        "duration_ms": round(duration * 1000.0, 3),
                    },
                )

    def record_quality_metric(self, metric: str, value: float) -> QualityConfidenceInterval:
        """Record a model quality metric observation and emit statistics."""

        samples = self._quality_samples[metric]
        samples.append(float(value))
        now = self._monotonic()
        self._get_series(f"quality.{metric}").append(now, float(value))

        interval = self._compute_confidence_interval(metric, samples)
        self._quality_intervals[metric] = interval
        self._metrics.set_model_quality_interval(
            self._config.model_name,
            self._config.environment,
            metric,
            interval.confidence_level,
            mean=interval.mean,
            lower=interval.lower,
            upper=interval.upper,
        )
        self._check_quality_degradation(metric, interval, now)
        return interval

    def configure_quality_baseline(
        self,
        metric: str,
        *,
        target: float,
        tolerance: float,
        min_samples: int | None = None,
    ) -> None:
        """Register a baseline describing the acceptable range for *metric*."""

        minimum = max(min_samples or self._config.quality_min_samples, 1)
        baseline = QualityBaseline(
            metric=metric,
            target=float(target),
            tolerance=abs(float(tolerance)),
            min_samples=minimum,
        )
        self._quality_baselines[metric] = baseline

    def update_resource_usage(
        self,
        snapshot: ResourceSnapshot | None = None,
        *,
        sampler: Callable[[], ResourceSnapshot] | None = None,
    ) -> ResourceSnapshot:
        """Record resource usage and update the associated metrics."""

        if snapshot is None:
            sampler_fn = sampler or self._default_resource_sampler
            snapshot = sampler_fn()

        self._last_resource_snapshot = snapshot
        now = self._monotonic()

        self._metrics.set_model_resource_usage(
            self._config.model_name,
            self._config.environment,
            cpu_percent=snapshot.cpu_percent,
            gpu_percent=snapshot.gpu_percent,
            memory_bytes=snapshot.memory_bytes,
            memory_percent=snapshot.memory_percent,
        )

        self._get_series("cpu_percent").append(now, snapshot.cpu_percent)
        self._get_series("memory_percent").append(now, snapshot.memory_percent)
        self._get_series("memory_bytes").append(now, snapshot.memory_bytes)
        if snapshot.gpu_percent is not None:
            self._get_series("gpu_percent").append(now, snapshot.gpu_percent)

        if snapshot.saturation is not None:
            bounded = max(0.0, min(1.0, float(snapshot.saturation)))
            self._metrics.set_model_saturation(
                self._config.model_name, self._config.environment, bounded
            )
            self._get_series("saturation").append(now, bounded)

        if snapshot.cache_name is not None:
            self._metrics.set_model_cache_metrics(
                self._config.model_name,
                self._config.environment,
                snapshot.cache_name,
                hit_ratio=snapshot.cache_hit_ratio,
                entries=snapshot.cache_entries,
            )
            if snapshot.cache_hit_ratio is not None:
                self._get_series(f"cache.hit_ratio.{snapshot.cache_name}").append(
                    now, snapshot.cache_hit_ratio
                )
            if snapshot.cache_entries is not None:
                self._get_series(f"cache.entries.{snapshot.cache_name}").append(
                    now, snapshot.cache_entries
                )
            if snapshot.cache_evictions:
                self._metrics.increment_model_cache_evictions(
                    self._config.model_name,
                    self._config.environment,
                    snapshot.cache_name,
                    snapshot.cache_evictions,
                )

        return snapshot

    def update_correlations(
        self,
        metric_pairs: Iterable[tuple[str, str]],
        *,
        window: int | None = None,
    ) -> Dict[tuple[str, str], float]:
        """Compute correlations for ``metric_pairs`` and publish gauges."""

        results: Dict[tuple[str, str], float] = {}
        for metric_a, metric_b in metric_pairs:
            coefficient = self.compute_correlation(metric_a, metric_b, window=window)
            if coefficient is None:
                continue
            results[(metric_a, metric_b)] = coefficient
            self._metrics.set_model_metric_correlation(
                self._config.model_name,
                self._config.environment,
                metric_a,
                metric_b,
                coefficient,
            )
        return results

    def compute_correlation(
        self, metric_a: str, metric_b: str, *, window: int | None = None
    ) -> float | None:
        """Return the Pearson correlation coefficient for two tracked metrics."""

        series_a = self._series.get(metric_a)
        series_b = self._series.get(metric_b)
        if series_a is None or series_b is None:
            return None

        values_a = series_a.values(window)
        values_b = series_b.values(window)
        length = min(len(values_a), len(values_b))
        if length < 2:
            return None

        paired_a = values_a[-length:]
        paired_b = values_b[-length:]
        try:
            coefficient = statistics.correlation(paired_a, paired_b)
        except statistics.StatisticsError:
            return None
        if math.isnan(coefficient):
            return None
        return coefficient

    def label_event(self, name: str, tags: Mapping[str, object] | None = None) -> EventLabel:
        """Attach a label to an operational event and retain it in the timeline."""

        label = EventLabel(name=name, tags=dict(tags or {}), timestamp=self._now())
        self._events.append(label)
        return label

    def generate_postmortem_template(self, event: DegradationSignal) -> PostmortemTemplate:
        """Build a structured postmortem template for *event*."""

        incident_id = event.incident.identifier if event.incident else "(untriaged)"
        contributing: Dict[str, object] = {
            "metric": event.metric,
            "observed": round(event.observed_value, 6),
            "severity": round(event.severity, 6),
        }
        if event.expected_value is not None:
            contributing["expected"] = round(event.expected_value, 6)
        interval = self._quality_intervals.get(event.metric)
        if interval is not None:
            contributing["confidence_interval"] = (
                round(interval.lower, 6),
                round(interval.upper, 6),
            )

        template = PostmortemTemplate(
            incident_id=incident_id,
            summary=(
                f"{self._config.model_name} {event.metric} degradation detected: {event.reason}"
            ),
            started_at=event.timestamp,
            detected_by="model-observability-orchestrator",
            severity=self._config.incident_severity,
            timeline=list(self._events),
            contributing_metrics=contributing,
            remediation_hypotheses=(
                "Validate recent deployments",
                "Re-run shadow evaluations",
            ),
            guardrails=(
                "Confidence intervals monitored continuously",
                "Latency SLAs enforced via Prometheus alerts",
            ),
        )
        return template

    @property
    def latest_degradations(self) -> tuple[DegradationSignal, ...]:
        """Return a snapshot of the recently emitted degradation signals."""

        return tuple(self._degradations)

    @property
    def incident_library(self) -> Mapping[str, IncidentRecord]:
        """Return a read-only view over persisted incidents."""

        return dict(self._incident_library)

    @property
    def quality_intervals(self) -> Mapping[str, QualityConfidenceInterval]:
        """Return the latest confidence intervals keyed by metric."""

        return dict(self._quality_intervals)

    @property
    def events(self) -> Sequence[EventLabel]:
        """Return the recorded event timeline."""

        return list(self._events)

    # ------------------------------------------------------------------
    # Internal helpers

    def _finalise_inference(
        self,
        *,
        duration: float,
        success: bool,
        status: str,
    ) -> None:
        duration = max(0.0, float(duration))
        self._metrics.observe_model_inference_latency(
            self._config.model_name, self._config.environment, duration
        )
        self._metrics.increment_model_inference_total(
            self._config.model_name, self._config.environment, status
        )

        now = self._monotonic()
        self._get_series("latency_seconds").append(now, duration)

        throughput, error_ratio = self._update_inference_statistics(now, success)
        self._metrics.set_model_inference_throughput(
            self._config.model_name, self._config.environment, throughput
        )
        self._metrics.set_model_inference_error_ratio(
            self._config.model_name, self._config.environment, error_ratio
        )
        self._get_series("throughput_per_second").append(now, throughput)
        self._get_series("error_ratio").append(now, error_ratio)

        saturation = self._compute_saturation(throughput)
        if saturation is not None:
            self._metrics.set_model_saturation(
                self._config.model_name, self._config.environment, saturation
            )
            self._get_series("saturation").append(now, saturation)

        if not success:
            self.label_event("inference.error", {"status": status})

        self._check_latency_degradation(duration, now)
        self._check_error_rate_degradation(error_ratio, now)

    def _update_inference_statistics(self, now: float, success: bool) -> tuple[float, float]:
        window = float(self._config.throughput_window_seconds)
        self._inference_events.append((now, success))
        while self._inference_events and now - self._inference_events[0][0] > window:
            self._inference_events.popleft()

        total = len(self._inference_events)
        throughput = total / window if window > 0 else float(total)
        errors = sum(1 for _, ok in self._inference_events if not ok)
        error_ratio = errors / total if total else 0.0
        return throughput, error_ratio

    def _compute_saturation(self, throughput: float) -> float | None:
        capacity = self._config.max_requests_per_second
        if capacity and capacity > 0:
            return max(0.0, min(1.0, throughput / float(capacity)))
        snapshot = self._last_resource_snapshot
        if snapshot is not None:
            if snapshot.saturation is not None:
                return max(0.0, min(1.0, float(snapshot.saturation)))
            return max(0.0, min(1.0, snapshot.cpu_percent / 100.0))
        return None

    def _check_latency_degradation(self, duration: float, now: float) -> None:
        threshold = self._config.latency_sla_ms
        if threshold is None:
            return
        if duration * 1000.0 <= threshold:
            return
        reason = f"latency exceeded {threshold}ms SLA"
        expected = threshold / 1000.0
        self._emit_degradation("latency", duration, expected, reason, now)

    def _check_error_rate_degradation(self, error_ratio: float, now: float) -> None:
        threshold = self._config.error_rate_threshold
        if threshold is None:
            return
        if error_ratio <= threshold:
            return
        reason = f"error ratio above threshold ({threshold:.3f})"
        self._emit_degradation("error_rate", error_ratio, threshold, reason, now)

    def _check_quality_degradation(
        self, metric: str, interval: QualityConfidenceInterval, now: float
    ) -> None:
        baseline = self._quality_baselines.get(metric)
        if baseline is None:
            return
        if interval.sample_size < baseline.min_samples:
            return

        lower_bound = baseline.target - baseline.tolerance
        upper_bound = baseline.target + baseline.tolerance
        if lower_bound <= interval.mean <= upper_bound:
            return

        reason = (
            f"quality mean outside target band {baseline.target:.4f} ± {baseline.tolerance:.4f}"
        )
        self._emit_degradation(metric, interval.mean, baseline.target, reason, now)

    def _emit_degradation(
        self,
        metric: str,
        observed: float,
        expected: float | None,
        reason: str,
        now: float,
    ) -> DegradationSignal | None:
        # The cooldown needs to be applied per-metric rather than per-reason. Some
        # reasons include live metric values (for example, quality mean deviations),
        # and embedding those in the key would make each emission unique and bypass
        # the cooldown entirely.
        key = metric
        last = self._last_degradation_by_metric.get(key)
        if last is not None:
            cooldown = self._config.degradation_cooldown_seconds
            if now - last < cooldown:
                return None

        severity = self._compute_degradation_severity(metric, observed, expected)

        event = DegradationSignal(
            metric=metric,
            observed_value=observed,
            expected_value=expected,
            severity=severity,
            reason=reason,
            timestamp=self._now(),
        )
        self._degradations.append(event)
        self._last_degradation_by_metric[key] = now
        self._metrics.record_model_degradation(
            self._config.model_name, self._config.environment, metric, reason
        )
        self.label_event(
            "model.degradation",
            {
                "metric": metric,
                "reason": reason,
                "observed": round(observed, 6),
                "expected": None if expected is None else round(expected, 6),
            },
        )
        if self._config.triage_on_degradation:
            self._launch_triage(event)
        return event

    def _launch_triage(self, event: DegradationSignal) -> None:
        try:
            record = self._incident_manager.create(
                title=(f"{self._config.model_name} {event.metric} degradation"),
                description=(
                    f"Automated triage triggered due to {event.reason}.\n"
                    f"Observed value: {event.observed_value:.6f}."
                ),
                metadata={
                    "metric": event.metric,
                    "observed": event.observed_value,
                    "expected": event.expected_value,
                    "severity": event.severity,
                },
                severity=self._config.incident_severity,
            )
        except Exception:  # pragma: no cover - filesystem failures
            LOGGER.exception("Failed to persist automated triage incident")
            return

        self._incident_library[record.identifier] = record
        event.incident = record
        self._metrics.record_model_triage(
            self._config.model_name,
            self._config.environment,
            event.metric,
            event.reason,
        )

    def _compute_degradation_severity(
        self, metric: str, observed: float, expected: float | None
    ) -> float:
        """Calibrate the severity of a degradation using metric context."""

        baseline = self._quality_baselines.get(metric)
        if baseline is not None:
            tolerance = max(float(baseline.tolerance), 1e-9)
            deviation = abs(float(observed) - float(baseline.target))
            overshoot = max(0.0, deviation - float(baseline.tolerance))
            return overshoot / tolerance

        if expected is None:
            return 0.0

        expected_value = abs(float(expected))
        if expected_value < 1e-6:
            expected_value = max(abs(float(observed)), 1.0)
        return max(0.0, abs(float(observed) - float(expected)) / expected_value)

    def _compute_confidence_interval(
        self, metric: str, samples: Sequence[float]
    ) -> QualityConfidenceInterval:
        cleaned = [float(value) for value in samples if math.isfinite(value)]
        if not cleaned:
            return QualityConfidenceInterval(
                metric=metric,
                mean=0.0,
                lower=0.0,
                upper=0.0,
                confidence_level=self._config.confidence_level,
                sample_size=0,
                stddev=0.0,
                timestamp=self._now(),
            )

        mean = float(statistics.mean(cleaned))
        sample_size = len(cleaned)
        if sample_size > 1:
            stddev = float(statistics.stdev(cleaned))
        else:
            stddev = 0.0

        if sample_size <= 1 or stddev == 0.0:
            lower = upper = mean
        else:
            alpha = 1.0 - self._config.confidence_level
            # Guard against invalid alpha due to floating point rounding.
            alpha = max(alpha, 1e-9)
            z_value = statistics.NormalDist().inv_cdf(1.0 - alpha / 2.0)
            margin = z_value * stddev / math.sqrt(sample_size)
            lower = mean - margin
            upper = mean + margin

        return QualityConfidenceInterval(
            metric=metric,
            mean=mean,
            lower=lower,
            upper=upper,
            confidence_level=self._config.confidence_level,
            sample_size=sample_size,
            stddev=stddev,
            timestamp=self._now(),
        )

    def _default_resource_sampler(self) -> ResourceSnapshot:
        if not _PSUTIL_AVAILABLE:
            raise RuntimeError(
                "psutil is required for automatic resource sampling but is not installed"
            )

        if self._process is not None:
            cpu_percent = float(self._process.cpu_percent(interval=None))
            memory_info = self._process.memory_info()
            memory_bytes = float(memory_info.rss)
            memory_percent = float(self._process.memory_percent())
        else:  # pragma: no cover - fallback when process handle unavailable
            cpu_percent = float(psutil.cpu_percent(interval=None))
            proc = psutil.Process()
            memory_info = proc.memory_info()
            memory_bytes = float(memory_info.rss)
            memory_percent = float(proc.memory_percent())

        return ResourceSnapshot(
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            memory_bytes=memory_bytes,
        )

    def _get_series(self, name: str) -> MetricSeries:
        series = self._series.get(name)
        if series is None:
            series = MetricSeries(name=name, maxlen=self._config.metric_history_size)
            self._series[name] = series
        return series


__all__ = [
    "DegradationSignal",
    "EventLabel",
    "InferenceContext",
    "ModelObservabilityConfig",
    "ModelObservabilityOrchestrator",
    "PostmortemTemplate",
    "QualityBaseline",
    "QualityConfidenceInterval",
    "ResourceSnapshot",
]
