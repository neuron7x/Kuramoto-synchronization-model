"""Runtime integration hooks for WML in TradePulse hot paths.

This module provides the integration layer between WML and TradePulse's
execution paths: ingest, features, signal, and execution.
"""

import os
import time
from typing import Callable, List

from core.adaptive_optimization.tacl_wml import (
    WML,
    WMLConfig,
    RegimeDetector,
    AuditLogger,
    RecordingEventBus,
)
from core.adaptive_optimization.tacl_wml.adapters.system_actions import SystemActions
from core.adaptive_optimization.tacl_wml.adapters.canary_probe import CanaryProbe
from core.adaptive_optimization.tacl_wml.metrics import Telemetry


# Enable/disable WML via environment
ENABLED = os.getenv("TP_WML_ENABLED", "true").lower() == "true"


def _current_vol_proxy() -> float:
    """Proxy for current market/system volatility.

    TODO: Connect to actual volatility indicator from TradePulse.
    For now, returns a moderate baseline.
    """
    return 0.5


def make_wml(risk_freeze_fn: Callable[[], bool]) -> WML:
    """Create and configure WML instance for TradePulse.

    Args:
        risk_freeze_fn: Function that returns True if system should freeze
                       (e.g., EWS=KILL or ES>limit)

    Returns:
        Configured WML instance
    """
    # Create base config
    cfg = WMLConfig()

    # Override from environment
    cfg.gamma_is = float(os.getenv("TP_WML_GAMMA_IS", "0.02"))
    cfg.eps_rel = float(os.getenv("TP_WML_EPS", "0.03"))
    cfg.min_apply_interval_s = float(os.getenv("TP_WML_MIN_APPLY_INTERVAL_S", "0.2"))
    cfg.auto_freeze_fails = int(os.getenv("TP_WML_AUTO_FREEZE_FAILS", "2"))

    # Validate configuration
    cfg.validate()

    # Create detector
    det = RegimeDetector(cfg.regime_thresholds, hysteresis_vol=cfg.hysteresis_vol)

    # Create WML with system actions
    return WML(
        cfg,
        det,
        actions=SystemActions(control_base_url=os.getenv("TP_CONTROL_URL")),
        audit=AuditLogger(),
        bus=RecordingEventBus(),
        risk_freeze_fn=risk_freeze_fn,
    )


def timeit_ms(fn: Callable[[], None], samples: int = 32) -> List[float]:
    """Time a function execution multiple times.

    Args:
        fn: Function to time
        samples: Number of samples to collect

    Returns:
        List of execution times in milliseconds
    """
    results = []
    for _ in range(samples):
        t0 = time.perf_counter()
        fn()
        t1 = time.perf_counter()
        results.append((t1 - t0) * 1000.0)
    return results


def step_hot_path(
    wml: WML, path: str, fn: Callable[[], None], is_bp: float = 0.0
) -> bool:
    """Execute WML optimization step for a hot path.

    This should be called periodically (e.g., every N iterations) in hot paths:
    - quotes_ingest: Parser/resampling
    - feature_pipe: Kuramoto/Ricci/Topo computation
    - signal_decide: Signal generation pipeline
    - order_execute: Order planning/submission

    Args:
        wml: WML instance
        path: Hot path identifier (e.g., "feature_pipe")
        fn: Function to time/optimize
        is_bp: Implementation shortfall in basis points (for execution path)

    Returns:
        True if optimization was applied, False otherwise

    Example:
        ```python
        from runtime.hooks_wml import make_wml, step_hot_path

        # Initialize once
        wml = make_wml(risk_freeze_fn=lambda: False)

        # In hot path loop
        def compute_features():
            # ... your feature computation code ...
            pass

        if step_hot_path(wml, "feature_pipe", compute_features):
            print("WML applied optimization")
        ```
    """
    if not ENABLED:
        return False

    # Measure current performance
    latencies = timeit_ms(fn, samples=32)

    # Create telemetry
    telem = Telemetry(
        latency_ms=latencies,
        resource_cost=0.0,  # TODO: Add actual resource tracking
        pnl_delta=0.0,  # TODO: Add actual PnL tracking
        vol_index=_current_vol_proxy(),
        is_bp=is_bp,
    )

    # Create probe for tentative measurements
    probe = CanaryProbe(
        mode="callable", fn=fn, samples=16, timeout_s=0.3, pnl_fn=lambda: 0.0
    )

    # Execute WML step
    return wml.step(path, telem, probe)
