# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for execution.risk.core module."""

from __future__ import annotations

import pytest

try:
    from execution.risk.core import RiskError
except ImportError:
    pytest.skip("module not importable", allow_module_level=True)


class TestRiskError:
    def test_is_runtime_error(self):
        err = RiskError("limit breached")
        assert isinstance(err, RuntimeError)
        assert str(err) == "limit breached"

    def test_can_be_caught_as_runtime_error(self):
        with pytest.raises(RuntimeError):
            raise RiskError("test")
