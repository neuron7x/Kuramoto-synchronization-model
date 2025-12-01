"""AAR integration with NaK neuro-controllers.

This module provides the integration layer between AAR error signals
and the neuromodulator-based adaptation system. It translates AAR
feedback into modulation of dopamine and serotonin-like signals.

Key Functions:
    aar_dopamine_modulation: Modulate dopamine based on positive errors
    aar_serotonin_modulation: Modulate serotonin based on negative errors
    compute_aar_adaptation: Compute adaptation signals from AAR stats

See nak_controller/docs/AAR_SPEC.md for full specification.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.state import clip
from .aggregators import AggregateStats


@dataclass
class AARAdaptationConfig:
    """Configuration for AAR-driven adaptation.

    Attributes:
        max_adaptation_step: Maximum change per adaptation cycle [0, 1].
        min_samples: Minimum samples before adaptation is active.
        positive_threshold: Error threshold for positive reinforcement.
        negative_threshold: Error threshold for negative suppression.
        catastrophic_threshold: Error level considered catastrophic.
        freeze_variance_threshold: Variance threshold for freeze mode.
        dopamine_sensitivity: Sensitivity of dopamine to positive errors.
        serotonin_sensitivity: Sensitivity of serotonin to negative errors.
    """

    max_adaptation_step: float = 0.1
    min_samples: int = 10
    positive_threshold: float = 0.1
    negative_threshold: float = -0.1
    catastrophic_threshold: float = 0.8
    freeze_variance_threshold: float = 0.5
    dopamine_sensitivity: float = 0.5
    serotonin_sensitivity: float = 0.5


@dataclass
class AARAdaptationState:
    """State tracking for AAR-driven adaptation.

    Attributes:
        is_frozen: Whether adaptation is frozen due to instability.
        freeze_reason: Reason for freeze if frozen.
        historical_mean: Historical mean error for drift detection.
        historical_std: Historical std for variance monitoring.
        adaptation_count: Number of adaptations applied.
        cumulative_dopamine_adjustment: Total dopamine adjustment applied.
        cumulative_serotonin_adjustment: Total serotonin adjustment applied.
    """

    is_frozen: bool = False
    freeze_reason: str = ""
    historical_mean: float = 0.0
    historical_std: float = 0.0
    adaptation_count: int = 0
    cumulative_dopamine_adjustment: float = 0.0
    cumulative_serotonin_adjustment: float = 0.0


@dataclass
class AARAdaptationResult:
    """Result of AAR adaptation computation.

    Attributes:
        dopamine_adjustment: Adjustment to apply to dopamine signal.
        serotonin_adjustment: Adjustment to apply to serotonin signal.
        should_reduce_risk: Whether risk should be reduced.
        risk_reduction_factor: Factor to reduce risk by (1.0 = no change).
        is_frozen: Whether adaptation is in frozen state.
        freeze_reason: Reason for freeze if applicable.
        metrics: Dictionary of computed metrics for observability.
    """

    dopamine_adjustment: float = 0.0
    serotonin_adjustment: float = 0.0
    should_reduce_risk: bool = False
    risk_reduction_factor: float = 1.0
    is_frozen: bool = False
    freeze_reason: str = ""
    metrics: dict[str, float] = field(default_factory=dict)


def aar_dopamine_modulation(
    stats: AggregateStats,
    config: AARAdaptationConfig,
) -> float:
    """Compute dopamine modulation from AAR statistics.

    Positive errors (outcomes better than expected) increase dopamine,
    which reinforces current behavior.

    Args:
        stats: Aggregated AAR statistics.
        config: Adaptation configuration.

    Returns:
        Dopamine adjustment in [-1, 1], positive = reinforcement.
    """
    if stats.count < config.min_samples:
        return 0.0

    # Base adjustment from mean error
    if stats.mean > config.positive_threshold:
        # Positive performance → dopamine boost
        raw_adjustment = stats.mean * config.dopamine_sensitivity
    else:
        raw_adjustment = 0.0

    # Additional boost from positive/negative ratio
    if stats.count > 0:
        positive_ratio = stats.positive_count / stats.count
        if positive_ratio > 0.7:
            # Strong positive trend
            raw_adjustment += 0.1 * config.dopamine_sensitivity

    # Clamp to max step
    return clip(raw_adjustment, -config.max_adaptation_step, config.max_adaptation_step)


def aar_serotonin_modulation(
    stats: AggregateStats,
    config: AARAdaptationConfig,
) -> float:
    """Compute serotonin modulation from AAR statistics.

    Negative errors (outcomes worse than expected) increase serotonin,
    which promotes caution and risk reduction.

    Args:
        stats: Aggregated AAR statistics.
        config: Adaptation configuration.

    Returns:
        Serotonin adjustment in [0, 1], higher = more caution.
    """
    if stats.count < config.min_samples:
        return 0.0

    # Base adjustment from mean error
    serotonin = 0.0
    if stats.mean < config.negative_threshold:
        # Negative performance → serotonin increase
        serotonin = abs(stats.mean) * config.serotonin_sensitivity

    # Additional increase from negative ratio
    if stats.count > 0:
        negative_ratio = stats.negative_count / stats.count
        if negative_ratio > 0.5:
            serotonin += 0.1 * config.serotonin_sensitivity

    # Additional increase from catastrophic rate
    if stats.catastrophic_rate > 0.1:
        serotonin += stats.catastrophic_rate * 0.5 * config.serotonin_sensitivity

    # Clamp to max step
    return clip(serotonin, 0.0, config.max_adaptation_step)


def should_freeze_adaptation(
    stats: AggregateStats,
    state: AARAdaptationState,
    config: AARAdaptationConfig,
) -> tuple[bool, str]:
    """Determine if adaptation should be frozen due to instability.

    Freezing occurs when:
    - Error variance exceeds threshold
    - Error mean shifts dramatically from historical baseline

    Args:
        stats: Current AAR statistics.
        state: Current adaptation state.
        config: Adaptation configuration.

    Returns:
        Tuple of (should_freeze, reason).
    """
    if stats.count < config.min_samples:
        return False, ""

    # Check variance threshold
    if stats.std > config.freeze_variance_threshold:
        return (
            True,
            f"High error variance: {stats.std:.4f} > {config.freeze_variance_threshold}",
        )

    # Check for dramatic mean shift (if we have historical baseline)
    if state.historical_std > 1e-6:
        z_score = abs(stats.mean - state.historical_mean) / state.historical_std
        if z_score > 3.0:
            return True, f"Mean shift detected: z-score={z_score:.2f}"

    # Check catastrophic rate
    if stats.catastrophic_rate > 0.2:
        return True, f"High catastrophic rate: {stats.catastrophic_rate:.2%}"

    return False, ""


def compute_risk_reduction(
    stats: AggregateStats,
    config: AARAdaptationConfig,
) -> float:
    """Compute risk reduction factor based on AAR statistics.

    Returns a factor in [0.5, 1.0] where:
    - 1.0 = no risk reduction
    - 0.5 = maximum risk reduction (50%)

    Args:
        stats: Aggregated AAR statistics.
        config: Adaptation configuration.

    Returns:
        Risk reduction factor.
    """
    if stats.count < config.min_samples:
        return 1.0

    # Start with full risk
    factor = 1.0

    # Reduce based on negative error mean
    if stats.mean < config.negative_threshold:
        reduction = min(0.3, abs(stats.mean) * 0.5)
        factor -= reduction

    # Further reduce based on catastrophic rate
    if stats.catastrophic_rate > 0.05:
        reduction = min(0.2, stats.catastrophic_rate)
        factor -= reduction

    return clip(factor, 0.5, 1.0)


def compute_aar_adaptation(
    stats: AggregateStats,
    state: AARAdaptationState,
    config: AARAdaptationConfig | None = None,
) -> AARAdaptationResult:
    """Compute comprehensive AAR adaptation result.

    This function combines all AAR adaptation logic into a single result
    that can be applied to the neuro-controller.

    Args:
        stats: Current AAR statistics.
        state: Current adaptation state.
        config: Adaptation configuration (uses default if None).

    Returns:
        AARAdaptationResult with all adaptation signals.
    """
    if config is None:
        config = AARAdaptationConfig()

    # Check freeze conditions
    should_freeze, freeze_reason = should_freeze_adaptation(stats, state, config)

    if should_freeze or state.is_frozen:
        return AARAdaptationResult(
            is_frozen=True,
            freeze_reason=freeze_reason or state.freeze_reason,
            metrics={
                "aar_error_mean": stats.mean,
                "aar_error_std": stats.std,
                "aar_positive_rate": stats.positive_count / max(1, stats.count),
                "aar_negative_rate": stats.negative_count / max(1, stats.count),
                "aar_catastrophic_rate": stats.catastrophic_rate,
                "aar_is_frozen": 1.0,
            },
        )

    # Compute modulations
    dopamine_adj = aar_dopamine_modulation(stats, config)
    serotonin_adj = aar_serotonin_modulation(stats, config)

    # Compute risk reduction
    risk_factor = compute_risk_reduction(stats, config)
    should_reduce = risk_factor < 1.0

    return AARAdaptationResult(
        dopamine_adjustment=dopamine_adj,
        serotonin_adjustment=serotonin_adj,
        should_reduce_risk=should_reduce,
        risk_reduction_factor=risk_factor,
        is_frozen=False,
        freeze_reason="",
        metrics={
            "aar_error_mean": stats.mean,
            "aar_error_std": stats.std,
            "aar_positive_rate": stats.positive_count / max(1, stats.count),
            "aar_negative_rate": stats.negative_count / max(1, stats.count),
            "aar_catastrophic_rate": stats.catastrophic_rate,
            "aar_dopamine_adjustment": dopamine_adj,
            "aar_serotonin_adjustment": serotonin_adj,
            "aar_risk_factor": risk_factor,
            "aar_is_frozen": 0.0,
        },
    )


def update_adaptation_state(
    state: AARAdaptationState,
    stats: AggregateStats,
    result: AARAdaptationResult,
) -> None:
    """Update adaptation state based on current stats and result.

    This function should be called after applying adaptation to update
    the state for the next cycle.

    Args:
        state: State to update (modified in place).
        stats: Current AAR statistics.
        result: Result of adaptation computation.
    """
    # Update freeze state
    state.is_frozen = result.is_frozen
    state.freeze_reason = result.freeze_reason

    # Update historical baseline (exponential moving average)
    alpha = 0.1  # Smoothing factor
    if stats.count >= 10:
        state.historical_mean = alpha * stats.mean + (1 - alpha) * state.historical_mean
        state.historical_std = alpha * stats.std + (1 - alpha) * state.historical_std

    # Track cumulative adjustments
    if not result.is_frozen:
        state.cumulative_dopamine_adjustment += result.dopamine_adjustment
        state.cumulative_serotonin_adjustment += result.serotonin_adjustment
        state.adaptation_count += 1


__all__ = [
    "AARAdaptationConfig",
    "AARAdaptationState",
    "AARAdaptationResult",
    "aar_dopamine_modulation",
    "aar_serotonin_modulation",
    "should_freeze_adaptation",
    "compute_risk_reduction",
    "compute_aar_adaptation",
    "update_adaptation_state",
]
