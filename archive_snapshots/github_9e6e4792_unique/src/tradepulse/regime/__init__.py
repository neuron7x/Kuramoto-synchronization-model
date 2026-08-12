"""TradePulse regime detection module."""

__CANONICAL__ = True

from .ews import EWSAggregator, EWSConfig, EWSResult

__all__ = ["EWSAggregator", "EWSConfig", "EWSResult"]
