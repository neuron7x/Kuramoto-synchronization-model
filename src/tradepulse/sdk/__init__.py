"""Public SDK for integrating with the TradePulse core.

This module provides a clean, user-friendly API for integrating TradePulse
trading capabilities into external systems. The SDK exposes two main modules:

1. **Trading SDK** (this module): Order execution, risk checks, and trading flows.
2. **MLSDM SDK** (mlsdm submodule): Multi-Level Stochastic Decision Model for
   adaptive decision-making with neuro-inspired components.

Example usage::

    from tradepulse.sdk import TradePulseSDK, MarketState, SDKConfig
    from tradepulse.sdk.mlsdm import MLSDM, create_fhmc

    # Trading SDK
    sdk = TradePulseSDK(system, config)
    signal = sdk.get_signal(market_state)
    proposal = sdk.propose_trade(signal)

    # MLSDM SDK
    mlsdm = MLSDM.default()
    biomarkers = mlsdm.get_biomarkers()
    action = mlsdm.act(observation)
"""

__CANONICAL__ = True

# Re-export MLSDM submodule for convenience
from . import mlsdm
from .contracts import (
    AuditEvent,
    ExecutionResult,
    MarketState,
    RiskCheckResult,
    SDKConfig,
    SuggestedOrder,
)
from .engine import TradePulseSDK

__all__ = [
    # Trading SDK
    "TradePulseSDK",
    "AuditEvent",
    "ExecutionResult",
    "MarketState",
    "RiskCheckResult",
    "SDKConfig",
    "SuggestedOrder",
    # MLSDM submodule
    "mlsdm",
]
