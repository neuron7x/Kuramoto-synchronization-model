# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Continuous response quality assurance orchestrator.

This module implements a comprehensive framework for validating model
responses against golden datasets, ensuring schema/contracts stay stable,
and coordinating human-in-the-loop review workflows. The orchestrator is
used to enforce quality gates for GeoSync inference workloads.
"""

from __future__ import annotations

import logging
import statistics
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import (
    Callable,
    Deque,
    Dict,
    Iterable,
    Mapping,
    MutableMapping,
    Sequence,
    Tuple,
)

from core.compat import utc_now
from core.utils.metrics import get_metrics_collector

from .incidents import IncidentManager
from .model_monitoring import DegradationSignal

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class GoldenRecord:
    """Single golden example used to validate model responses."""

    identifier: str
    request: Mapping[str, object]
    expected: Mapping[str, object]
    tags: Tuple[str, ...] = ()

    def matches_tags(self, tags: set[str]) -> bool:
        if not tags:
            return True
        return bool(tags.intersection(self.tags))


@dataclass(slots=True, frozen=True)
class GoldenDataset:
    """Versioned collection of golden records."""

    name: str
    version: str
    records: Tuple[GoldenRecord, ...]
    description: str = ""
    metadata: Mapping[str, object] = field(default_factory=dict)

    def filtered_records(self, tags: set[str]) -> Tuple[GoldenRecord, ...]:
        if not tags:
            return self.records
        return tuple(record for record in self.records if record.matches_tags(tags))

    def merge(
        self, records: Iterable[GoldenRecord], *, version: str | None = None
    ) -> "GoldenDataset":
        """Return a dataset with ``records`` merged into the existing collection."""

        updated: MutableMapping[str, GoldenRecord] = {
            record.identifier: record for record in self.records
        }
        order: list[str] = [record.identifier for record in self.records]
        for record in records:
            key = record.identifier
            updated[key] = record
            if key not in order:
                order.append(key)
        merged_records = tuple(updated[key] for key in order)
        return GoldenDataset(
            name=self.name,
            version=version or self.version,
            records=merged_records,
            description=self.description,
            metadata=self.metadata,
        )


@dataclass(slots=True, frozen=True)
class QualityContractViolation:
    """Contract failure observed during validation."""

    contract: str
    message: str
    details: Mapping[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class QualityContract:
    """Declarative description of guarantees a response must satisfy."""

    name: str
    description: str
    validator: Callable[
        [Mapping[str, object]],
        Sequence[QualityContractViolation] | QualityContractViolation | None,
    ]

    def validate(self, response: Mapping[str, object]) -> Tuple[QualityContractViolation, ...]:
        result = self.validator(response)
        if result is None:
            return ()
        if isinstance(result, QualityContractViolation):
            return (result,)
        return tuple(result)


@dataclass(slots=True, frozen=True)
class QualityFailure:
    """Failure encountered while checking a golden record."""

    dataset: str
    record_id: str
    reason: str
    expected: Mapping[str, object] | None
    actual: Mapping[str, object] | None
    tags: Tuple[str, ...]
    details: Mapping[str, object] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class QualityRunSummary:
    """Aggregate summary describing an evaluation run."""

    dataset: str
    version: str
    total: int
    matches: int
    mismatches: int
    contract_failures: int
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    score: float
    partial: bool
    tags: Tuple[str, ...]
    failures: Tuple[QualityFailure, ...]
    latency_avg_ms: float
    latency_p50_ms: float
    latency_p95_ms: float


@dataclass(slots=True, frozen=True)
class ReviewTicket:
    """Ticket representing a human review request."""

    identifier: str
    dataset: str
    record_id: str
    reason: str
    details: Mapping[str, object]
    status: str = "pending"
    created_at: datetime = field(default_factory=lambda: utc_now())
    resolved_at: datetime | None = None
    reviewer: str | None = None
    notes: str | None = None

    def resolve(
        self, reviewer: str, *, notes: str | None = None, status: str = "resolved"
    ) -> "ReviewTicket":
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "reviewer", reviewer)
        object.__setattr__(self, "notes", notes)
        object.__setattr__(self, "resolved_at", utc_now())
        return self


@dataclass(slots=True, frozen=True)
class ComplaintRecord:
    """User complaint routed to the appropriate quality team."""

    identifier: str
    category: str
    message: str
    route: str
    metadata: Mapping[str, object]
    created_at: datetime = field(default_factory=lambda: utc_now())


@dataclass(slots=True, frozen=True)
class ActiveSample:
    """Sample selected for focused inspection via active sampling."""

    identifier: str
    request: Mapping[str, object]
    response: Mapping[str, object]
    score: float
    source: str
    created_at: datetime = field(default_factory=lambda: utc_now())


@dataclass(slots=True, frozen=True)
class ImprovementLog:
    """Continuous improvement action captured by the pipeline."""

    identifier: str
    description: str
    owner: str | None
    status: str
    metadata: Mapping[str, object]
    created_at: datetime = field(default_factory=lambda: utc_now())


@dataclass(slots=True, frozen=True)
class DatasetBaseline:
    """Baseline expectation for a dataset's aggregate score."""

    dataset: str
    score: float
    tolerance: float
    version: str
    updated_at: datetime = field(default_factory=lambda: utc_now())


@dataclass(slots=True)
class ResponseQualityConfig:
    """Configuration for :class:`ResponseQualityOrchestrator`."""

    model_name: str
    environment: str = "production"
    schedule_interval_seconds: float = 3600.0
    baseline_tolerance: float = 0.02
    degrade_on_contract_failure: bool = True
    max_review_queue: int = 128
    max_active_samples: int = 256
    active_sampling_threshold: float = 0.2
    complaint_default_route: str = "quality.ops"
    auto_triage: bool = True
    incident_severity: str = "minor"
    incident_root: str | Path | None = None
    degradation_cooldown_seconds: float = 600.0

    def __post_init__(self) -> None:
        if self.schedule_interval_seconds <= 0:
            raise ValueError("schedule_interval_seconds must be positive")
        if not (0.0 <= self.baseline_tolerance <= 1.0):
            raise ValueError("baseline_tolerance must be within [0, 1]")
        if self.max_review_queue <= 0:
            raise ValueError("max_review_queue must be positive")
        if self.max_active_samples <= 0:
            raise ValueError("max_active_samples must be positive")
        if self.active_sampling_threshold < 0.0:
            raise ValueError("active_sampling_threshold cannot be negative")
        if self.degradation_cooldown_seconds < 0.0:
            raise ValueError("degradation_cooldown_seconds cannot be negative")


class ResponseQualityOrchestrator:
    """Orchestrate continuous response quality verification."""

    def __init__(
        self,
        config: ResponseQualityConfig,
        responder: Callable[[Mapping[str, object]], Mapping[str, object] | object],
        *,
        incident_manager: IncidentManager | None = None,
        monotonic: Callable[[], float] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._responder = responder
        self._metrics = get_metrics_collector()
        self._monotonic = monotonic or time.monotonic
        self._now = now or (lambda: utc_now())

        if incident_manager is not None:
            self._incident_manager = incident_manager
        else:
            root = Path(config.incident_root) if config.incident_root else None
            self._incident_manager = IncidentManager(root)

        self._datasets: Dict[str, GoldenDataset] = {}
        self._contracts: Dict[str, QualityContract] = {}
        self._baselines: Dict[str, DatasetBaseline] = {}
        self._baseline_summaries: Dict[str, QualityRunSummary] = {}
        self._last_run_at: float | None = None
        self._degradations: Deque[DegradationSignal] = deque(maxlen=256)
        self._last_degradation_time: Dict[str, float] = {}

        self._reviews: Dict[str, ReviewTicket] = {}
        self._review_queue: Deque[str] = deque()
        self._complaint_routes: Dict[
            str, Callable[[str, Mapping[str, object] | None], str] | str
        ] = {}
        self._complaints: Deque[ComplaintRecord] = deque(maxlen=512)
        self._reason_map: Counter[str] = Counter()
        self._active_samples: Deque[ActiveSample] = deque(maxlen=config.max_active_samples)
        self._improvements: Dict[str, ImprovementLog] = {}

        self._ticket_counter = 0
        self._complaint_counter = 0
        self._sample_counter = 0
        self._improvement_counter = 0

    # ------------------------------------------------------------------
    # Registration helpers

    def register_golden_dataset(self, dataset: GoldenDataset) -> None:
        """Register or replace a golden dataset."""

        self._datasets[dataset.name] = dataset

    def update_golden_dataset(
        self, name: str, records: Iterable[GoldenRecord], *, version: str | None = None
    ) -> None:
        """Merge ``records`` into the named dataset."""

        dataset = self._datasets.get(name)
        if dataset is None:
            raise KeyError(f"Dataset '{name}' is not registered")
        merged = dataset.merge(records, version=version)
        self._datasets[name] = merged

    def register_contract(self, contract: QualityContract) -> None:
        """Register a response quality contract."""

        self._contracts[contract.name] = contract

    def configure_dataset_baseline(
        self,
        dataset: str,
        *,
        score: float,
        tolerance: float | None = None,
        version: str = "baseline",
    ) -> None:
        """Configure the baseline expectations for ``dataset``."""

        tolerance_value = self._config.baseline_tolerance if tolerance is None else tolerance
        if tolerance_value < 0.0:
            raise ValueError("tolerance cannot be negative")
        baseline = DatasetBaseline(
            dataset=dataset,
            score=float(score),
            tolerance=float(tolerance_value),
            version=version,
        )
        self._baselines[dataset] = baseline
        summary = QualityRunSummary(
            dataset=dataset,
            version=version,
            total=0,
            matches=0,
            mismatches=0,
            contract_failures=0,
            started_at=self._now(),
            completed_at=self._now(),
            duration_seconds=0.0,
            score=float(score),
            partial=False,
            tags=(),
            failures=(),
            latency_avg_ms=0.0,
            latency_p50_ms=0.0,
            latency_p95_ms=0.0,
        )
        self._baseline_summaries[dataset] = summary

    def register_complaint_route(
        self,
        category: str,
        handler: Callable[[str, Mapping[str, object] | None], str] | str,
    ) -> None:
        """Register routing strategy for complaint ``category``."""

        self._complaint_routes[category] = handler

    # ------------------------------------------------------------------
    # Execution

    def run_golden_checks(
        self,
        *,
        datasets: Iterable[str] | None = None,
        tags: Iterable[str] | None = None,
    ) -> Dict[str, QualityRunSummary]:
        """Execute golden dataset checks, optionally filtered by ``tags``."""

        dataset_names = list(datasets) if datasets is not None else sorted(self._datasets)
        tag_set = {str(tag) for tag in (tags or ())}
        summaries: Dict[str, QualityRunSummary] = {}
        for name in dataset_names:
            dataset = self._datasets.get(name)
            if dataset is None:
                LOGGER.warning("Dataset '%s' not registered; skipping", name)
                continue
            records = dataset.filtered_records(tag_set)
            if not records and tag_set:
                continue
            summary = self._evaluate_dataset(dataset, records, tag_set)
            summaries[name] = summary
        if summaries:
            self._last_run_at = self._monotonic()
        return summaries

    def run_automated_checks(
        self, *, tags: Iterable[str] | None = None
    ) -> Dict[str, QualityRunSummary]:
        """Run checks if the schedule interval has elapsed."""

        now = self._monotonic()
        if (
            self._last_run_at is not None
            and now - self._last_run_at < self._config.schedule_interval_seconds
        ):
            return {}
        return self.run_golden_checks(tags=tags)

    # ------------------------------------------------------------------
    # Human review lifecycle

    def pending_reviews(self) -> Tuple[ReviewTicket, ...]:
        return tuple(self._reviews[ticket_id] for ticket_id in self._review_queue)

    def resolve_review(
        self,
        ticket_id: str,
        reviewer: str,
        *,
        notes: str | None = None,
        status: str = "resolved",
    ) -> ReviewTicket:
        ticket = self._reviews.get(ticket_id)
        if ticket is None:
            raise KeyError(f"Review ticket '{ticket_id}' not found")
        updated = ticket.resolve(reviewer, notes=notes, status=status)
        self._reviews[ticket_id] = updated
        if ticket_id in self._review_queue:
            self._review_queue.remove(ticket_id)
        self._update_pending_reviews_metric()
        return updated

    # ------------------------------------------------------------------
    # Complaints and improvements

    def route_complaint(
        self,
        category: str,
        message: str,
        *,
        metadata: Mapping[str, object] | None = None,
    ) -> ComplaintRecord:
        handler = self._complaint_routes.get(category)
        if callable(handler):
            route = handler(category, metadata)
        elif isinstance(handler, str):
            route = handler
        else:
            route = self._config.complaint_default_route
        self._complaint_counter += 1
        identifier = f"CMP-{self._complaint_counter:05d}"
        record = ComplaintRecord(
            identifier=identifier,
            category=category,
            message=message,
            route=route,
            metadata=dict(metadata or {}),
        )
        self._complaints.append(record)
        self._metrics.record_response_quality_complaint(
            self._config.model_name,
            self._config.environment,
            category,
            route,
        )
        self._record_reason(f"complaint:{category}")
        return record

    def complaints(self) -> Tuple[ComplaintRecord, ...]:
        return tuple(self._complaints)

    def record_improvement(
        self,
        description: str,
        *,
        owner: str | None = None,
        status: str = "planned",
        metadata: Mapping[str, object] | None = None,
    ) -> ImprovementLog:
        self._improvement_counter += 1
        identifier = f"IMP-{self._improvement_counter:05d}"
        record = ImprovementLog(
            identifier=identifier,
            description=description,
            owner=owner,
            status=status,
            metadata=dict(metadata or {}),
        )
        self._improvements[identifier] = record
        return record

    def improvements(self) -> Tuple[ImprovementLog, ...]:
        return tuple(self._improvements.values())

    # ------------------------------------------------------------------
    # Active sampling

    def record_live_response(
        self,
        request: Mapping[str, object],
        response: Mapping[str, object],
        *,
        confidence: float | None = None,
        source: str = "live",
    ) -> ActiveSample | None:
        request_payload = _normalise_payload(request)
        response_payload = _normalise_payload(response)
        score = float(
            confidence if confidence is not None else response_payload.get("confidence", 1.0)
        )
        if score >= self._config.active_sampling_threshold:
            return None
        self._sample_counter += 1
        identifier = f"SMP-{self._sample_counter:05d}"
        sample = ActiveSample(
            identifier=identifier,
            request=request_payload,
            response=response_payload,
            score=score,
            source=source,
        )
        self._active_samples.append(sample)
        return sample

    def next_active_sample(self) -> ActiveSample | None:
        if not self._active_samples:
            return None
        return self._active_samples.popleft()

    def active_samples(self) -> Tuple[ActiveSample, ...]:
        return tuple(self._active_samples)

    # ------------------------------------------------------------------
    # Observability

    def latest_degradations(self) -> Tuple[DegradationSignal, ...]:
        return tuple(self._degradations)

    def baselines(self) -> Mapping[str, DatasetBaseline]:
        return dict(self._baselines)

    def baseline_summaries(self) -> Mapping[str, QualityRunSummary]:
        return dict(self._baseline_summaries)

    def reason_map(self) -> Mapping[str, int]:
        return dict(self._reason_map)

    # ------------------------------------------------------------------
    # Internal helpers

    def _evaluate_dataset(
        self,
        dataset: GoldenDataset,
        records: Sequence[GoldenRecord],
        tag_filter: set[str],
    ) -> QualityRunSummary:
        started_at = self._now()
        start_perf = self._monotonic()
        matches = 0
        mismatches = 0
        contract_failures = 0
        failures: list[QualityFailure] = []
        latencies_ms: list[float] = []

        for record in records:
            request_payload = _normalise_payload(record.request)
            invocation_start = self._monotonic()
            try:
                raw_response = self._responder(request_payload)
                response_payload = _normalise_payload(raw_response)
            except (
                Exception
            ) as exc:  # pragma: no cover - defensive logging path exercised via tests
                LOGGER.exception(
                    "Failed to evaluate record '%s' in dataset '%s'",
                    record.identifier,
                    dataset.name,
                )
                mismatches += 1
                failure = QualityFailure(
                    dataset=dataset.name,
                    record_id=record.identifier,
                    reason="exception",
                    expected=record.expected,
                    actual={},
                    tags=record.tags,
                    details={"exception": repr(exc)},
                )
                failures.append(failure)
                self._enqueue_review(failure)
                continue
            finally:
                latency = max(0.0, (self._monotonic() - invocation_start) * 1000.0)
                latencies_ms.append(latency)

            diff = _diff_payloads(record.expected, response_payload)
            if diff:
                mismatches += 1
                failure = QualityFailure(
                    dataset=dataset.name,
                    record_id=record.identifier,
                    reason="mismatch",
                    expected=record.expected,
                    actual=response_payload,
                    tags=record.tags,
                    details={"differences": diff},
                )
                failures.append(failure)
                self._enqueue_review(failure)
            else:
                matches += 1

            for violation in self._evaluate_contracts(dataset.name, response_payload):
                contract_failures += 1
                failure = QualityFailure(
                    dataset=dataset.name,
                    record_id=record.identifier,
                    reason=f"contract:{violation.contract}",
                    expected=record.expected,
                    actual=response_payload,
                    tags=record.tags,
                    details=dict(violation.details, message=violation.message),
                )
                failures.append(failure)
                self._enqueue_review(failure)
                if self._config.degrade_on_contract_failure:
                    self._emit_degradation(
                        metric=f"{dataset.name}.contracts",
                        observed=float(contract_failures),
                        expected=0.0,
                        reason=f"Contract '{violation.contract}' violated",
                        severity=1.0 + float(contract_failures),
                    )

        completed_at = self._now()
        duration_seconds = max(0.0, self._monotonic() - start_perf)
        total = matches + mismatches
        score = matches / total if total else 1.0
        partial = bool(tag_filter) or total != len(dataset.records)
        latency_avg = statistics.fmean(latencies_ms) if latencies_ms else 0.0
        latency_p50 = _percentile(latencies_ms, 50.0)
        latency_p95 = _percentile(latencies_ms, 95.0)

        summary = QualityRunSummary(
            dataset=dataset.name,
            version=dataset.version,
            total=total,
            matches=matches,
            mismatches=mismatches,
            contract_failures=contract_failures,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration_seconds,
            score=score,
            partial=partial,
            tags=tuple(sorted(tag_filter)),
            failures=tuple(failures),
            latency_avg_ms=latency_avg,
            latency_p50_ms=latency_p50,
            latency_p95_ms=latency_p95,
        )

        status = "pass" if mismatches == 0 and contract_failures == 0 else "fail"
        mode = "partial" if partial else "full"
        self._metrics.record_response_quality_run(
            self._config.model_name,
            self._config.environment,
            dataset.name,
            mode,
            status,
            duration_seconds,
        )
        self._update_pending_reviews_metric()
        self._check_against_baseline(summary)
        return summary

    def _evaluate_contracts(
        self,
        dataset: str,
        response: Mapping[str, object],
    ) -> Tuple[QualityContractViolation, ...]:
        violations: list[QualityContractViolation] = []
        for contract in self._contracts.values():
            try:
                failures = contract.validate(response)
            except Exception as exc:  # pragma: no cover - contract errors should be surfaced
                LOGGER.exception("Contract '%s' validation failed", contract.name)
                failure = QualityContractViolation(
                    contract=contract.name,
                    message="validator raised exception",
                    details={"exception": repr(exc)},
                )
                failures = (failure,)
            for violation in failures:
                violations.append(violation)
                self._metrics.record_response_quality_contract_violation(
                    self._config.model_name,
                    self._config.environment,
                    dataset,
                    violation.contract,
                )
        return tuple(violations)

    def _check_against_baseline(self, summary: QualityRunSummary) -> None:
        baseline = self._baselines.get(summary.dataset)
        if baseline is None:
            return
        tolerance = (
            baseline.tolerance
            if baseline.tolerance > 0.0
            else max(self._config.baseline_tolerance, 1e-6)
        )
        delta = baseline.score - summary.score
        if delta <= tolerance:
            return
        severity = delta / tolerance
        reason = (
            f"Dataset '{summary.dataset}' score dropped by {delta:.4f} (tolerance {tolerance:.4f})"
        )
        self._emit_degradation(
            metric=f"{summary.dataset}.score",
            observed=summary.score,
            expected=baseline.score,
            reason=reason,
            severity=severity,
        )

    def _emit_degradation(
        self,
        *,
        metric: str,
        observed: float,
        expected: float | None,
        reason: str,
        severity: float,
    ) -> None:
        now = self._monotonic()
        last = self._last_degradation_time.get(metric)
        if last is not None and now - last < self._config.degradation_cooldown_seconds:
            return
        self._last_degradation_time[metric] = now
        event = DegradationSignal(
            metric=metric,
            observed_value=float(observed),
            expected_value=None if expected is None else float(expected),
            severity=max(0.0, float(severity)),
            reason=reason,
        )
        self._degradations.append(event)
        self._metrics.record_response_quality_degradation(
            self._config.model_name,
            self._config.environment,
            metric.split(".", 1)[0],
            reason,
        )
        self._record_reason(reason)
        if self._config.auto_triage:
            try:
                record = self._incident_manager.create(
                    title=f"Response quality degradation: {metric}",
                    description=(
                        f"Automated degradation trigger for {metric}.\n"
                        f"Observed: {observed:.6f}, Expected: {expected!r}.\nReason: {reason}"
                    ),
                    metadata={
                        "metric": metric,
                        "observed": observed,
                        "expected": expected,
                        "severity": severity,
                    },
                    severity=self._config.incident_severity,
                )
            except Exception:  # pragma: no cover - filesystem failures
                LOGGER.exception("Failed to persist response quality incident")
            else:
                event.incident = record

    def _enqueue_review(self, failure: QualityFailure) -> None:
        self._ticket_counter += 1
        identifier = f"RVW-{self._ticket_counter:05d}"
        ticket = ReviewTicket(
            identifier=identifier,
            dataset=failure.dataset,
            record_id=failure.record_id,
            reason=failure.reason,
            details=failure.details,
        )
        if len(self._review_queue) >= self._config.max_review_queue:
            oldest = self._review_queue.popleft()
            self._reviews.pop(oldest, None)
        self._review_queue.append(identifier)
        self._reviews[identifier] = ticket
        self._metrics.record_response_quality_reason(
            self._config.model_name,
            self._config.environment,
            f"review:{failure.reason}",
        )
        self._update_pending_reviews_metric()

    def _update_pending_reviews_metric(self) -> None:
        self._metrics.set_response_quality_pending_reviews(
            self._config.model_name,
            self._config.environment,
            len(self._review_queue),
        )

    def _record_reason(self, reason: str) -> None:
        self._reason_map[reason] += 1
        self._metrics.record_response_quality_reason(
            self._config.model_name,
            self._config.environment,
            reason,
        )


def _normalise_payload(payload: Mapping[str, object] | object) -> Mapping[str, object]:
    if isinstance(payload, Mapping):
        return dict(payload)
    if hasattr(payload, "model_dump"):
        return dict(payload.model_dump())
    if hasattr(payload, "dict"):
        return dict(payload.dict())
    raise TypeError("Payload must be a mapping or provide model_dump()/dict()")


def _diff_payloads(
    expected: Mapping[str, object], actual: Mapping[str, object]
) -> Mapping[str, Tuple[object, object]]:
    diff: Dict[str, Tuple[object, object]] = {}
    for key, expected_value in expected.items():
        actual_value = actual.get(key)
        if actual_value != expected_value:
            diff[str(key)] = (expected_value, actual_value)
    return diff


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    rank = (percentile / 100.0) * (len(sorted_values) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = rank - lower
    return float(sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight)


__all__ = [
    "ActiveSample",
    "ComplaintRecord",
    "DatasetBaseline",
    "GoldenDataset",
    "GoldenRecord",
    "ImprovementLog",
    "QualityContract",
    "QualityContractViolation",
    "QualityFailure",
    "QualityRunSummary",
    "ResponseQualityConfig",
    "ResponseQualityOrchestrator",
    "ReviewTicket",
]
