# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Prompt template library with experiment and rollback capabilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from random import Random
from typing import Dict, Mapping

from .exceptions import PromptExperimentError, PromptTemplateNotFoundError
from .models import PromptOutcome, PromptTemplate

__all__ = [
    "PromptVariantMetrics",
    "PromptExperiment",
    "PromptTemplateLibrary",
]


@dataclass(slots=True)
class PromptVariantMetrics:
    """Track performance metrics for a prompt variant."""

    renders: int = 0
    successes: int = 0
    failures: int = 0
    effect_sum: float = 0.0
    effect_samples: int = 0

    def register_render(self) -> None:
        self.renders += 1

    def record_outcome(self, outcome: PromptOutcome) -> None:
        if outcome.success:
            self.successes += 1
        else:
            self.failures += 1
        if outcome.effect is not None:
            self.effect_sum += outcome.effect
            self.effect_samples += 1

    @property
    def failure_rate(self) -> float:
        if self.renders == 0:
            return 0.0
        return self.failures / self.renders

    @property
    def average_effect(self) -> float | None:
        if self.effect_samples == 0:
            return None
        return self.effect_sum / self.effect_samples


@dataclass(slots=True)
class PromptExperiment:
    """Configuration describing an active prompt experiment."""

    name: str
    control_variant: str
    allocations: Mapping[str, float]
    min_samples: int = 30
    failure_threshold: float = 0.35
    effect_floor: float | None = None
    seed: int = 1
    _metrics: Dict[str, PromptVariantMetrics] = field(init=False, default_factory=dict)
    _rng: Random = field(init=False)
    active: bool = field(init=False, default=True)

    def __post_init__(self) -> None:
        if self.control_variant not in self.allocations:
            raise PromptExperimentError(
                f"control variant '{self.control_variant}' missing from allocations"
            )
        total = sum(self.allocations.values())
        if not 0.999 <= total <= 1.001:
            raise PromptExperimentError("variant allocations must sum to 1.0")
        if self.min_samples <= 0:
            raise PromptExperimentError("min_samples must be positive")
        if not 0.0 < self.failure_threshold < 1.0:
            raise PromptExperimentError("failure_threshold must be between 0 and 1")
        object.__setattr__(self, "_metrics", {})
        object.__setattr__(self, "_rng", Random(self.seed))
        object.__setattr__(self, "active", True)

    @property
    def metrics(self) -> Mapping[str, PromptVariantMetrics]:
        return self._metrics

    def select_variant(self, assignment: float | None = None) -> str:
        """Select a variant using *assignment* or RNG when absent."""

        if not self.active:
            return self.control_variant
        value = assignment
        if value is None:
            value = self._rng.random()
        if not 0.0 <= value < 1.0:
            raise PromptExperimentError("assignment must be within [0, 1)")

        cumulative = 0.0
        for variant, weight in self.allocations.items():
            cumulative += weight
            if value < cumulative:
                return variant
        return self.control_variant

    def register_render(self, variant: str) -> None:
        metrics = self._metrics.setdefault(variant, PromptVariantMetrics())
        metrics.register_render()

    def record_outcome(self, variant: str, outcome: PromptOutcome) -> bool:
        metrics = self._metrics.setdefault(variant, PromptVariantMetrics())
        metrics.record_outcome(outcome)
        if variant == self.control_variant:
            return False
        if metrics.renders < self.min_samples:
            return False
        if metrics.failure_rate >= self.failure_threshold:
            return True
        if (
            self.effect_floor is not None
            and metrics.average_effect is not None
            and metrics.average_effect < self.effect_floor
        ):
            return True
        return False

    def stop(self) -> None:
        self.active = False


@dataclass(slots=True)
class _PromptSuite:
    """Internal container for managing template variants."""

    templates: Dict[str, PromptTemplate]
    control_variant: str
    active_variant: str | None
    activation_log: list[tuple[str, str]] = field(default_factory=list)
    experiment: PromptExperiment | None = None

    @classmethod
    def from_template(cls, template: PromptTemplate) -> "_PromptSuite":
        log = [(template.variant, "initial-control")]
        return cls(
            templates={template.variant: template},
            control_variant=template.variant,
            active_variant=None,
            activation_log=log,
        )

    def record_activation(self, variant: str, reason: str) -> None:
        self.activation_log.append((variant, reason))
        if variant == self.control_variant:
            self.active_variant = None
        else:
            self.active_variant = variant

    def get_variant(self, variant: str) -> PromptTemplate:
        try:
            return self.templates[variant]
        except KeyError as exc:  # pragma: no cover - defensive branch
            raise PromptTemplateNotFoundError(
                f"Variant '{variant}' not registered in suite"
            ) from exc

    def select_variant(self, assignment: float | None) -> str:
        if self.experiment and self.experiment.active:
            variant = self.experiment.select_variant(assignment)
            if variant not in self.templates:
                variant = self.control_variant
            self.experiment.register_render(variant)
            return variant
        return self.active_variant or self.control_variant

    def rollback_to_control(self, reason: str) -> None:
        self.record_activation(self.control_variant, reason)
        if self.experiment:
            self.experiment.stop()
            self.experiment = None


class PromptTemplateLibrary:
    """Manage prompt templates, experiments and rollback actions."""

    def __init__(self) -> None:
        self._suites: Dict[str, _PromptSuite] = {}

    def register(self, template: PromptTemplate, *, activate: bool = False) -> None:
        suite = self._suites.get(template.family)
        if suite is None:
            suite = _PromptSuite.from_template(template)
            self._suites[template.family] = suite
        else:
            suite.templates[template.variant] = template
            if template.variant == suite.control_variant:
                suite.record_activation(template.variant, "control-updated")
        if activate:
            self.activate_variant(
                template.family,
                template.variant,
                reason="manual-activation",
            )

    def activate_variant(self, family: str, variant: str, *, reason: str) -> None:
        suite = self._require_suite(family)
        if variant not in suite.templates:
            raise PromptTemplateNotFoundError(
                f"Variant '{variant}' is not registered under family '{family}'"
            )
        suite.record_activation(variant, reason)
        if suite.experiment and suite.experiment.active:
            suite.experiment.stop()
            suite.experiment = None

    def start_experiment(self, family: str, experiment: PromptExperiment) -> None:
        suite = self._require_suite(family)
        missing = [variant for variant in experiment.allocations if variant not in suite.templates]
        if missing:
            raise PromptExperimentError(
                f"Experiment variants not registered: {', '.join(sorted(missing))}"
            )
        suite.experiment = experiment

    def stop_experiment(self, family: str) -> None:
        suite = self._require_suite(family)
        if suite.experiment:
            suite.experiment.stop()
            suite.experiment = None

    def rollback(self, family: str, *, reason: str = "manual-rollback") -> None:
        suite = self._require_suite(family)
        suite.rollback_to_control(reason)

    def select_template(self, family: str, *, assignment: float | None = None) -> PromptTemplate:
        suite = self._require_suite(family)
        variant = suite.select_variant(assignment)
        return suite.get_variant(variant)

    def record_outcome(self, family: str, variant: str, outcome: PromptOutcome) -> bool:
        suite = self._require_suite(family)
        if suite.experiment and suite.experiment.active:
            rollback_required = suite.experiment.record_outcome(variant, outcome)
            if rollback_required:
                suite.rollback_to_control("experiment-rollback")
            return rollback_required
        return False

    def _require_suite(self, family: str) -> _PromptSuite:
        try:
            return self._suites[family]
        except KeyError as exc:  # pragma: no cover - defensive branch
            raise PromptTemplateNotFoundError(
                f"Prompt family '{family}' has not been registered"
            ) from exc
