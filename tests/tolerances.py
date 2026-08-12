# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Shared numeric tolerances to keep tests stable across platforms."""

from __future__ import annotations

from decimal import Decimal

from core.utils.determinism import THREAD_BOUND_ENV_VARS as _THREAD_BOUND_ENV_VARS

# Threading environment variables that should be pinned to a single worker
# when running tests to maximise reproducibility across BLAS backends and
# hardware architectures.  The values are represented as strings to match the
# expectations of ``os.environ``.
THREAD_BOUND_ENV_VARS: dict[str, str] = dict(_THREAD_BOUND_ENV_VARS)

# Relative tolerance for floating point comparisons across the suite.
FLOAT_REL_TOL = 1e-6

# Absolute tolerance for floating point comparisons.
FLOAT_ABS_TOL = 1e-6

# Timestamp comparisons are performed in seconds at float precision.
TIMESTAMP_ABS_TOL = 1e-6

# Decimal tolerance used when comparing high precision quantities.
DECIMAL_ABS_TOL = Decimal("1e-9")
