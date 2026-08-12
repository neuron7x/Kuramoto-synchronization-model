# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Energy validation primitives used by Thermodynamic Validation workflows.

The original post-merge regression was traced to an incorrect aggregation of
metric penalties while computing the Helmholtz free energy (:math:`F`).  The
legacy implementation accumulated weighted penalties without normalising by the
sum of weights which effectively double-counted high-sensitivity metrics.  The
resulting free energy overshot the admissible envelope even for nominal
latency, causing the ``validate-energy`` GitHub check to fail after merge.

This module reimplements the energy calculation with explicit weight
normalisation, stability-aware entropy, and ergonomic diagnostics that can be
consumed both by CI workflows and human operators.  The design prioritises
readability and determinism so the logic is easy to audit during incident
response.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Iterable, Mapping, MutableMapping

if TYPE_CHECKING:
    from .behavioral_contract import BehavioralContract, BehavioralContractReport


# Thresholds and weights follow the production tuning captured in incident
# retrospectives.  Values are expressed in the natural units of each metric
# (milliseconds for latency, percentages for packet loss and coherency drift,
# etc.).
DEFAULT_THRESHOLDS: Mapping[str, float] = {
    "latency_p95": 85.0,  # milliseconds
    "latency_p99": 120.0,  # milliseconds
    "coherency_drift": 0.08,  # dimensionless ratio (0-1)
    "cpu_burn": 0.75,  # cpu utilisation (0-1)
    "mem_cost": 6.5,  # gibibytes per node
    "queue_depth": 32.0,  # messages
    "packet_loss": 0.005,  # ratio (0-1)
}

DEFAULT_WEIGHTS: Mapping[str, float] = {
    "latency_p95": 1.6,
    "latency_p99": 1.9,
    "coherency_drift": 1.2,
    "cpu_burn": 0.9,
    "mem_cost": 0.8,
    "queue_depth": 0.7,
    "packet_loss": 1.4,
}


@dataclass(frozen=True, slots=True)
class EnergyMetrics:
    """Container for telemetry feeding the energy validator."""

    latency_p95: float
    latency_p99: float
    coherency_drift: float
    cpu_burn: float
    mem_cost: float
    queue_depth: float
    packet_loss: float

    def as_dict(self) -> Mapping[str, float]:
        return {
            "latency_p95": float(self.latency_p95),
            "latency_p99": float(self.latency_p99),
            "coherency_drift": float(self.coherency_drift),
            "cpu_burn": float(self.cpu_burn),
            "mem_cost": float(self.mem_cost),
            "queue_depth": float(self.queue_depth),
            "packet_loss": float(self.packet_loss),
        }


@dataclass(frozen=True, slots=True)
class EnergyValidationResult:
    """Normalized outcome of an energy validation cycle."""

    passed: bool
    free_energy: float
    internal_energy: float
    entropy: float
    penalties: Mapping[str, float]
    reason: str | None = None


class EnergyValidationError(RuntimeError):
    """Raised when the energy validation rejects telemetry."""

    def __init__(self, message: str, result: EnergyValidationResult) -> None:
        super().__init__(message)
        self.result = result


class EnergyModel:
    """Compute Helmholtz free energy for GeoSync metrics.

    The model treats each metric as a penalty scaled by an importance weight.
    Penalties are normalised by the sum of weights to avoid overshooting the
    admissible range, fixing the regression that triggered the failed CI gate.
    Entropy increases when metrics sit comfortably below their thresholds which
    mirrors the stabilising effect of slack resources.
    """

    def __init__(
        self,
        *,
        thresholds: Mapping[str, float] = DEFAULT_THRESHOLDS,
        weights: Mapping[str, float] = DEFAULT_WEIGHTS,
        base_internal_energy: float = 0.92,
        temperature: float = 0.6,
        entropy_floor: float = 0.05,
    ) -> None:
        if thresholds.keys() != weights.keys():
            missing_from_weights = thresholds.keys() - weights.keys()
            missing_from_thresholds = weights.keys() - thresholds.keys()
            raise ValueError(
                "thresholds and weights must reference the same metrics"
                f" (missing weights: {sorted(missing_from_weights)},"
                f" missing thresholds: {sorted(missing_from_thresholds)})"
            )
        self._thresholds = {name: float(value) for name, value in thresholds.items()}
        self._weights = {name: float(weight) for name, weight in weights.items()}
        weight_total = sum(self._weights.values())
        if weight_total <= 0:
            raise ValueError("weights must sum to a positive value")
        self._normalised_weights = {
            name: weight / weight_total for name, weight in self._weights.items()
        }
        self._base_internal_energy = float(base_internal_energy)
        self._temperature = float(temperature)
        self._entropy_floor = float(entropy_floor)

    @property
    def metrics(self) -> Iterable[str]:
        return self._thresholds.keys()

    def _penalty(self, name: str, value: float) -> float:
        threshold = self._thresholds[name]
        if threshold <= 0:
            return 0.0
        ratio = value / threshold
        return max(ratio - 1.0, 0.0)

    def _stability(self, name: str, value: float) -> float:
        threshold = self._thresholds[name]
        if threshold <= 0:
            return 0.0
        ratio = value / threshold
        return max(0.0, 1.0 - ratio)

    def diagnostics(self, metrics: EnergyMetrics) -> Mapping[str, float]:
        """Return per-metric penalties used by the model."""

        penalties: MutableMapping[str, float] = {}
        for name, value in metrics.as_dict().items():
            penalties[name] = self._penalty(name, value)
        return penalties

    def internal_energy(self, metrics: EnergyMetrics) -> float:
        penalties = self.diagnostics(metrics)
        weighted_penalty = sum(
            penalties[name] * self._normalised_weights[name] for name in penalties
        )
        return self._base_internal_energy + weighted_penalty

    def entropy(self, metrics: EnergyMetrics) -> float:
        stabilities = [
            self._stability(name, value) * self._normalised_weights[name]
            for name, value in metrics.as_dict().items()
        ]
        aggregate = sum(stabilities)
        entropy = max(self._entropy_floor, aggregate)
        return entropy

    def free_energy(
        self, metrics: EnergyMetrics
    ) -> tuple[float, float, float, Mapping[str, float]]:
        penalties = self.diagnostics(metrics)
        internal = self.internal_energy(metrics)
        entropy = self.entropy(metrics)
        free_energy = internal - self._temperature * entropy
        return free_energy, internal, entropy, penalties

    def evaluate(self, metrics: EnergyMetrics, *, max_free_energy: float) -> EnergyValidationResult:
        free_energy, internal, entropy, penalties = self.free_energy(metrics)
        passed = free_energy <= max_free_energy
        reason = None
        if not passed:
            reason = (
                f"free energy {free_energy:.3f} exceeds bound {max_free_energy:.3f}; "
                f"penalties={{{', '.join(f'{k}: {v:.3f}' for k, v in penalties.items())}}}"
            )
        return EnergyValidationResult(
            passed=passed,
            free_energy=free_energy,
            internal_energy=internal,
            entropy=entropy,
            penalties=penalties,
            reason=reason,
        )


class EnergyValidator:
    """Validate telemetry using :class:`EnergyModel`."""

    def __init__(
        self,
        *,
        thresholds: Mapping[str, float] | None = None,
        weights: Mapping[str, float] | None = None,
        max_free_energy: float = 1.4,
    ) -> None:
        self._model = EnergyModel(
            thresholds=thresholds or DEFAULT_THRESHOLDS,
            weights=weights or DEFAULT_WEIGHTS,
        )
        self._max_free_energy = float(max_free_energy)
        zero_payload = {name: 0.0 for name in self._model.metrics}
        zero_metrics = EnergyMetrics(**zero_payload)
        floor_free_energy, _, _, _ = self._model.free_energy(zero_metrics)
        self._contract_floor = float(floor_free_energy)

    @property
    def model(self) -> EnergyModel:
        return self._model

    @property
    def max_free_energy(self) -> float:
        return self._max_free_energy

    def evaluate(self, metrics: EnergyMetrics) -> EnergyValidationResult:
        return self._model.evaluate(metrics, max_free_energy=self._max_free_energy)

    def validate(self, metrics: EnergyMetrics) -> EnergyValidationResult:
        result = self.evaluate(metrics)
        if not result.passed:
            raise EnergyValidationError(result.reason or "energy validation failed", result)
        return result

    def enforce_contract(
        self,
        metrics_sequence: Iterable[EnergyMetrics],
        contract: "BehavioralContract",
        *,
        approvals: Iterable[str] | None = None,
    ) -> "BehavioralContractReport":
        """Evaluate a telemetry sequence and enforce a behavioural contract."""

        results = []
        for metrics in metrics_sequence:
            result = self.evaluate(metrics)
            if not result.passed:
                raise EnergyValidationError(
                    result.reason or "energy validation failed",
                    result,
                )
            results.append(result)

        shift = contract.rest_potential - self._contract_floor
        rebased = []
        for result in results:
            if result.free_energy > self._max_free_energy:
                if abs(shift) <= 1e-12:
                    message = (
                        f"free energy {result.free_energy:.3f} exceeds bound "
                        f"{self._max_free_energy:.3f}"
                    )
                else:
                    message = (
                        f"free energy {result.free_energy:.3f} exceeds bound "
                        f"{self._max_free_energy:.3f} before contract rebasing "
                        f"(shift={shift:.6f})"
                    )
                failure = replace(
                    result,
                    passed=False,
                    reason=message,
                )
                raise EnergyValidationError(message, failure)

            if abs(shift) <= 1e-12:
                rebased_result = result
            else:
                rebased_result = replace(
                    result,
                    free_energy=result.free_energy + shift,
                    internal_energy=result.internal_energy + shift,
                )

            if rebased_result.free_energy > self._max_free_energy:
                if abs(shift) <= 1e-12:
                    message = (
                        f"free energy {rebased_result.free_energy:.3f} exceeds bound "
                        f"{self._max_free_energy:.3f}"
                    )
                else:
                    message = (
                        f"rebased free energy {rebased_result.free_energy:.3f} exceeds bound "
                        f"{self._max_free_energy:.3f} (shift={shift:.6f})"
                    )
                failure = replace(
                    rebased_result,
                    passed=False,
                    reason=message,
                )
                raise EnergyValidationError(message, failure)

            rebased.append(rebased_result)

        return contract.enforce(rebased, approvals=approvals)


__all__ = [
    "DEFAULT_THRESHOLDS",
    "DEFAULT_WEIGHTS",
    "EnergyMetrics",
    "EnergyModel",
    "EnergyValidationError",
    "EnergyValidationResult",
    "EnergyValidator",
]
