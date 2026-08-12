# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Performance benchmarking and metrics collection for GeoSync.

This module provides standardized performance measurement capabilities for
the golden path backtest workflow and other critical trading paths.
"""

__CANONICAL__ = True

from .golden_path import run_golden_path_bench
from .io import write_perf_report

__all__ = ["run_golden_path_bench", "write_perf_report"]
