"""Utilities for ingesting, transforming and integrating macroeconomic datasets."""

from .clients import MacroDataClient, MacrosynergyClient
from .feature_engineering import MacroFeatureBuilder, MacroFeatureConfig
from .integration import integrate_macro_features
from .models import MacroIndicatorConfig
from .pipeline import MacroSignalPipeline

__all__ = [
    "MacroDataClient",
    "MacrosynergyClient",
    "MacroFeatureBuilder",
    "MacroFeatureConfig",
    "MacroIndicatorConfig",
    "MacroSignalPipeline",
    "integrate_macro_features",
]
