"""Utilities for generating automated tests across the TradePulse codebase."""

from .test_generator import (
    ComponentAnalysis,
    ModuleAnalysis,
    analyze_component,
    analyze_module,
    generate_unit_tests,
)

__all__ = [
    "ComponentAnalysis",
    "ModuleAnalysis",
    "analyze_component",
    "analyze_module",
    "generate_unit_tests",
]
