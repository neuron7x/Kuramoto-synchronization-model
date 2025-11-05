"""Minimum Free Energy calculation with IS penalty."""

from .metrics import Telemetry


def free_energy(t: Telemetry, alpha: float, beta: float, gamma_is: float) -> float:
    """Calculate free energy metric (lower is better).

    F = p99 + α·jitter + β·resource_cost + γ·IS_bp

    This represents the total "cost" of the system across multiple dimensions:
    - Latency (p99)
    - Stability (jitter)
    - Resource usage (cost)
    - Execution quality (implementation shortfall)

    Args:
        t: Telemetry data
        alpha: Weight for jitter component
        beta: Weight for resource cost component
        gamma_is: Weight for implementation shortfall component

    Returns:
        Free energy value (minimize this)
    """
    return (
        t.p99 + alpha * t.jitter + beta * t.resource_cost + gamma_is * max(0.0, t.is_bp)
    )
