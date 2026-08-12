# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Shared utilities for GeoSync."""

from .clock import freeze_time
from .debug import VariableInspector
from .logging import (
    JSONFormatter,
    StructuredLogger,
    configure_logging,
    get_logger,
)
from .metrics import (
    MetricsCollector,
    get_metrics_collector,
    start_metrics_server,
)
from .numeric_constants import (
    BINARY_PROB_MIN,
    CASH_TOLERANCE,
    DIV_SAFE_MIN,
    FLOAT32_EPS,
    FLOAT64_EPS,
    FLOAT_ABS_TOL,
    FLOAT_REL_TOL,
    LOG_SAFE_MIN,
    POSITION_SIZE_MIN,
    PROB_CLIP_MAX,
    PROB_CLIP_MIN,
    VARIANCE_SAFE_MIN,
    VOLATILITY_SAFE_MIN,
    ZERO_TOL,
    clip_probability,
    is_effectively_zero,
    safe_divide,
    safe_log,
    safe_sqrt,
)
from .slo import AutoRollbackGuard, SLOBurnRateRule, SLOConfig

__all__ = [
    "JSONFormatter",
    "StructuredLogger",
    "configure_logging",
    "get_logger",
    "MetricsCollector",
    "get_metrics_collector",
    "start_metrics_server",
    "AutoRollbackGuard",
    "SLOBurnRateRule",
    "SLOConfig",
    "freeze_time",
    "VariableInspector",
    # Numeric constants
    "FLOAT64_EPS",
    "FLOAT32_EPS",
    "DIV_SAFE_MIN",
    "LOG_SAFE_MIN",
    "VARIANCE_SAFE_MIN",
    "VOLATILITY_SAFE_MIN",
    "PROB_CLIP_MIN",
    "PROB_CLIP_MAX",
    "BINARY_PROB_MIN",
    "POSITION_SIZE_MIN",
    "CASH_TOLERANCE",
    "FLOAT_REL_TOL",
    "FLOAT_ABS_TOL",
    "ZERO_TOL",
    # Numeric helper functions
    "safe_divide",
    "safe_log",
    "safe_sqrt",
    "clip_probability",
    "is_effectively_zero",
]
