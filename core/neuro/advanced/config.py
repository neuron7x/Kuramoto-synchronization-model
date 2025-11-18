"""Configuration models for the advanced neuro module."""

from __future__ import annotations

from typing import Dict

from pydantic import BaseModel, Field, field_validator


class DPAConfig(BaseModel):
    """Configuration for the dopamine prediction network."""

    learning_rate: float = Field(0.1, gt=0.0, le=1.0)
    decay_rate: float = Field(0.95, gt=0.0, le=1.0)
    risk_modulation_min: float = Field(0.5, gt=0.0, le=10.0)
    risk_modulation_max: float = Field(2.0, gt=0.0, le=10.0)

    @field_validator("risk_modulation_max")
    @classmethod
    def _check_bounds(cls, value: float, info):
        min_value = info.data.get(
            "risk_modulation_min", cls.model_fields["risk_modulation_min"].default
        )
        if value < min_value:
            raise ValueError(
                "risk_modulation_max must be greater than or equal to risk_modulation_min"
            )
        return value


class AICConfig(BaseModel):
    """Configuration for the agency and insula control network."""

    initial_confidence: float = Field(0.7, ge=0.0, le=1.0)
    confidence_decay: float = Field(0.99, gt=0.0, le=1.0)
    learning_sensitivity: float = Field(0.1, ge=0.0, le=1.0)
    volatility_impact: float = Field(0.1, ge=0.0, le=1.0)
    loss_aversion_init: float = Field(1.5, ge=0.5, le=5.0)


class NREConfig(BaseModel):
    """Configuration for the neuroplastic reinforcement engine."""

    ltp_rate: float = Field(0.15, gt=0.0, le=1.0)
    ltd_rate: float = Field(0.1, gt=0.0, le=1.0)
    weight_decay: float = Field(0.995, gt=0.0, le=1.0)
    consolidation_threshold: float = Field(0.7, ge=0.0, le=1.0)
    max_memory_size: int = Field(2000, gt=0)


class AlertThresholds(BaseModel):
    """Alert thresholds used by the integrated system."""

    confidence_collapse: float = Field(0.3, ge=0.0, le=1.0)
    dopamine_spike: float = Field(0.85, ge=0.0, le=1.0)
    strategy_stagnation: float = Field(0.12, ge=0.0, le=1.0)


class DecisionIntegratorWeights(BaseModel):
    """Weights used by the decision integrator."""

    edge: float = Field(1.0, ge=0.0)
    size: float = Field(0.6, ge=0.0)
    inverse_risk: float = Field(0.35, ge=0.0)
    confidence: float = Field(0.5, ge=0.0)
    context_preference: float = Field(0.25, ge=0.0)


class PolicyBounds(BaseModel):
    """Bounds for policy outputs."""

    min_position: float = Field(0.05, gt=0.0, le=10.0)
    max_position: float = Field(3.0, gt=0.0, le=10.0)
    min_risk: float = Field(0.15, gt=0.0, le=5.0)
    max_risk: float = Field(2.0, gt=0.0, le=5.0)


class NeuroAdvancedConfig(BaseModel):
    """Top level configuration for the advanced neuro module."""

    dpa: DPAConfig = DPAConfig()
    aic: AICConfig = AICConfig()
    nre: NREConfig = NREConfig()
    history_size: int = Field(20000, gt=100)
    monitoring_enabled: bool = True
    alert_thresholds: AlertThresholds = AlertThresholds()
    slo_gate_confidence_min: float = Field(0.28, ge=0.0, le=1.0)
    slo_gate_max_volatility: float = Field(0.45, ge=0.0)
    slo_emergency_downscale: float = Field(0.3, gt=0.0, le=1.0)
    decision_weights: DecisionIntegratorWeights = DecisionIntegratorWeights()
    policy_bounds: PolicyBounds = PolicyBounds()

    def merged_alert_thresholds(self) -> Dict[str, float]:
        return self.alert_thresholds.model_dump()
