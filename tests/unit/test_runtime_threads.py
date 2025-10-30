# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests enforcing deterministic threading configuration for numeric libraries."""
from __future__ import annotations

import os

from tests.tolerances import THREAD_BOUND_ENV_VARS


def test_thread_bound_env_vars_are_pinned() -> None:
    """All thread-bound environment variables should be forced to a single worker."""

    for key, expected in THREAD_BOUND_ENV_VARS.items():
        assert os.environ.get(key) == expected
