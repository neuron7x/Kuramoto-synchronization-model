"""Release gating utilities combining latency, compliance, and checklist status."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping, Sequence

from execution.compliance import ComplianceReport


@dataclass(slots=True, frozen=True)
class ReleaseGateResult:
    """Outcome emitted by a release gating probe."""

    name: str
    passed: bool
    reason: str | None = None
    metrics: Mapping[str, float] = field(default_factory=dict)

    def raise_for_failure(self) -> None:
        """Raise ``RuntimeError`` when the gate failed.

        This is intended for CI jobs that should abort immediately if a gate is
        not satisfied. The exception message contains the human readable reason.
        """

        if self.passed:
            return
        raise RuntimeError(
            f"release gate '{self.name}' failed: {self.reason or 'unspecified reason'}"
        )


@dataclass(slots=True, frozen=True)
class LatencyBudget:
    """Latency thresholds that must be satisfied for a stage."""

    median_ms: float
    p95_ms: float
    max_ms: float


def _default_execution_latency_budgets() -> dict[str, LatencyBudget]:
    return {
        "market_to_signal": LatencyBudget(25.0, 60.0, 90.0),
        "signal_to_risk": LatencyBudget(12.0, 30.0, 60.0),
        "risk_to_order": LatencyBudget(18.0, 45.0, 75.0),
        "market_to_order": LatencyBudget(45.0, 90.0, 150.0),
    }


@dataclass(slots=True)
class ReleaseGateEvaluator:
    """Evaluate release criteria for latency, compliance, and checklists."""

    latency_median_target_ms: float = 40.0
    latency_p95_target_ms: float = 80.0
    latency_max_target_ms: float = 150.0
    execution_stage_budgets: Mapping[str, LatencyBudget] = field(
        default_factory=_default_execution_latency_budgets
    )

    def evaluate_latency(self, samples_ms: Sequence[float]) -> ReleaseGateResult:
        """Validate latency distribution against configured thresholds."""

        name = "latency"
        if not samples_ms:
            return ReleaseGateResult(name, False, "no latency samples provided")

        median = _percentile(samples_ms, 50.0)
        p95 = _percentile(samples_ms, 95.0)
        max_latency = max(samples_ms)
        metrics = {
            "median_ms": round(median, 3),
            "p95_ms": round(p95, 3),
            "max_ms": round(max_latency, 3),
            "count": float(len(samples_ms)),
        }
        if median > self.latency_median_target_ms:
            return ReleaseGateResult(
                name,
                False,
                reason=(
                    f"median latency {median:.3f}ms exceeds target"
                    f" {self.latency_median_target_ms:.3f}ms"
                ),
                metrics=metrics,
            )
        if p95 > self.latency_p95_target_ms:
            return ReleaseGateResult(
                name,
                False,
                reason=(
                    f"p95 latency {p95:.3f}ms exceeds target"
                    f" {self.latency_p95_target_ms:.3f}ms"
                ),
                metrics=metrics,
            )
        if max_latency > self.latency_max_target_ms:
            return ReleaseGateResult(
                name,
                False,
                reason=(
                    f"max latency {max_latency:.3f}ms exceeds hard limit"
                    f" {self.latency_max_target_ms:.3f}ms"
                ),
                metrics=metrics,
            )
        return ReleaseGateResult(name, True, metrics=metrics)

    def evaluate_execution_pipeline(
        self, stage_samples_ms: Mapping[str, Sequence[float]]
    ) -> ReleaseGateResult:
        """Validate latency budgets for each execution pipeline stage."""

        name = "execution_pipeline_latency"
        metrics: MutableMapping[str, float] = {}
        failures: list[str] = []
        for stage, budget in self.execution_stage_budgets.items():
            samples = stage_samples_ms.get(stage)
            if not samples:
                failures.append(f"{stage} missing samples")
                continue
            median = _percentile(samples, 50.0)
            p95 = _percentile(samples, 95.0)
            max_latency = max(samples)
            metrics[f"{stage}_median_ms"] = round(median, 3)
            metrics[f"{stage}_p95_ms"] = round(p95, 3)
            metrics[f"{stage}_max_ms"] = round(max_latency, 3)
            metrics[f"{stage}_count"] = float(len(samples))

            if median > budget.median_ms:
                failures.append(
                    f"{stage} median {median:.3f}ms exceeds {budget.median_ms:.3f}ms"
                )
            if p95 > budget.p95_ms:
                failures.append(
                    f"{stage} p95 {p95:.3f}ms exceeds {budget.p95_ms:.3f}ms"
                )
            if max_latency > budget.max_ms:
                failures.append(
                    f"{stage} max {max_latency:.3f}ms exceeds {budget.max_ms:.3f}ms"
                )

        if failures:
            return ReleaseGateResult(
                name,
                False,
                reason="; ".join(failures),
                metrics=metrics,
            )
        return ReleaseGateResult(name, True, metrics=metrics)

    def evaluate_compliance(
        self, reports: Sequence[ComplianceReport]
    ) -> ReleaseGateResult:
        """Ensure pre-trade compliance did not block or flag orders."""

        name = "compliance"
        if not reports:
            return ReleaseGateResult(name, False, "no compliance reports supplied")

        violations = 0
        blocked = 0
        for report in reports:
            if report.violations:
                violations += 1
            if report.blocked:
                blocked += 1
        metrics = {
            "checked": float(len(reports)),
            "violations": float(violations),
            "blocked": float(blocked),
        }
        if blocked:
            return ReleaseGateResult(
                name,
                False,
                reason=f"{blocked} compliance checks blocked execution",
                metrics=metrics,
            )
        if violations:
            return ReleaseGateResult(
                name,
                False,
                reason=f"{violations} compliance checks reported violations",
                metrics=metrics,
            )
        return ReleaseGateResult(name, True, metrics=metrics)

    def evaluate_checklist(self, checklist: Mapping[str, object]) -> ReleaseGateResult:
        """Validate that the production readiness checklist is complete."""

        name = "production_checklist"
        items = checklist.get("items") if isinstance(checklist, Mapping) else None
        if not isinstance(items, Iterable):
            return ReleaseGateResult(name, False, "malformed checklist payload")

        missing: list[str] = []
        total = 0
        for item in items:  # type: ignore[assignment]
            if not isinstance(item, Mapping):
                return ReleaseGateResult(name, False, "malformed checklist item")
            total += 1
            status = str(item.get("status", "")).strip().lower()
            key = str(item.get("key", f"item_{total}")).strip()
            if status != "complete":
                missing.append(key or f"item_{total}")
        metrics = {"items": float(total), "incomplete": float(len(missing))}
        if missing:
            return ReleaseGateResult(
                name,
                False,
                reason=f"incomplete checklist items: {', '.join(sorted(missing))}",
                metrics=metrics,
            )
        return ReleaseGateResult(name, True, metrics=metrics)

    def evaluate_checklist_from_path(self, path: Path) -> ReleaseGateResult:
        """Load and validate a checklist document from disk."""

        data = json.loads(path.read_text(encoding="utf-8"))
        return self.evaluate_checklist(data)

    def aggregate_results(
        self, results: Sequence[ReleaseGateResult]
    ) -> ReleaseGateResult:
        """Collapse individual gate results into a single release signal."""

        aggregate_metrics: MutableMapping[str, float] = {}
        failing: list[str] = []
        for result in results:
            aggregate_metrics[f"{result.name}_passed"] = 1.0 if result.passed else 0.0
            for key, value in result.metrics.items():
                aggregate_metrics[f"{result.name}_{key}"] = float(value)
            if not result.passed:
                failing.append(result.reason or result.name)
        if failing:
            return ReleaseGateResult(
                "aggregate",
                False,
                reason="; ".join(failing),
                metrics=aggregate_metrics,
            )
        return ReleaseGateResult("aggregate", True, metrics=aggregate_metrics)


def _percentile(values: Sequence[float], percentile: float) -> float:
    """Return percentile using linear interpolation."""

    if not values:
        raise ValueError("values must contain at least one sample")
    if percentile <= 0:
        return float(min(values))
    if percentile >= 100:
        return float(max(values))
    ordered = sorted(float(v) for v in values)
    rank = (percentile / 100.0) * (len(ordered) - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    weight = rank - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


__all__ = [
    "ReleaseGateEvaluator",
    "ReleaseGateResult",
]
