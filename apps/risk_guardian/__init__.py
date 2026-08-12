# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""GeoSync Risk Guardian — Automated risk control for trading strategies.

This module provides a simplified product layer that wraps GeoSync's
sophisticated risk engine into a single, easy-to-use interface for traders
who want automatic drawdown protection without building complex systems.

The Risk Guardian:
- Limits daily losses to a configurable threshold
- Triggers kill-switch at critical drawdown levels
- Automatically enters safe-mode at warning levels
- Provides clear, money-denominated reports

Usage:
    from apps.risk_guardian import RiskGuardian, RiskGuardianConfig

    config = RiskGuardianConfig(
        daily_loss_limit_pct=5.0,    # Max 5% loss per day
        max_drawdown_pct=10.0,       # Kill-switch at 10%
        safe_mode_threshold_pct=7.0, # Enter safe mode at 7%
    )

    guardian = RiskGuardian(config)
    result = guardian.simulate_from_prices(prices, signal_fn)
    print(result.summary())
"""

from .config import RiskGuardianConfig, SimulationResult
from .engine import RiskGuardian

__all__ = ["RiskGuardian", "RiskGuardianConfig", "SimulationResult"]
