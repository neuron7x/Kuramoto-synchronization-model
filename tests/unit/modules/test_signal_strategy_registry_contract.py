# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Defect-sensitive contracts for the signal strategy registry.

Covers duplicate-id rejection, unknown-id fail-closed behaviour, deterministic
signal output, the "never a None impl for a live strategy" guarantee, malformed
strategy-class rejection, and the disabled-strategy execution block.
"""

from __future__ import annotations

from typing import cast

import numpy as np
import pandas as pd
import pytest

from modules.signal_strategy_registry import (
    MomentumStrategy,
    SignalStrategyRegistry,
    StrategyCategory,
    StrategyInterface,
    StrategyMetadata,
    StrategyStatus,
)


def _meta(name: str = "s") -> StrategyMetadata:
    return StrategyMetadata(
        name=name,
        version="1.0.0",
        category=StrategyCategory.MOMENTUM,
        description="d",
        author="t",
        required_features={"close"},
    )


def _price_frame(n: int = 60, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100.0 + np.cumsum(rng.normal(0.0, 1.0, n))
    return pd.DataFrame({"close": close})


def test_duplicate_strategy_id_is_rejected() -> None:
    reg = SignalStrategyRegistry()
    reg.register(MomentumStrategy, _meta("dup"))
    with pytest.raises(ValueError, match="already registered"):
        reg.register(MomentumStrategy, _meta("dup"))


def test_unknown_strategy_fails_closed() -> None:
    reg = SignalStrategyRegistry()
    assert reg.get_strategy("ghost") is None
    assert reg.get_metadata("ghost") is None
    result = reg.validate_strategy("ghost", _price_frame())
    assert result.is_valid is False
    assert any("not found" in e for e in result.errors)


def test_registered_active_strategy_never_returns_none_impl() -> None:
    reg = SignalStrategyRegistry()
    reg.register(MomentumStrategy, _meta("mom"))
    impl = reg.get_strategy("mom")
    assert impl is not None
    assert isinstance(impl, StrategyInterface)


def test_signal_generation_is_deterministic() -> None:
    data = _price_frame()
    a = MomentumStrategy().generate_signals(data)
    b = MomentumStrategy().generate_signals(data)
    pd.testing.assert_frame_equal(a, b)


def test_malformed_strategy_class_is_rejected_under_strict_validation() -> None:
    reg = SignalStrategyRegistry(strict_validation=True)

    class NotAStrategy:  # does not inherit StrategyInterface
        pass

    with pytest.raises(ValueError, match="validation failed"):
        reg.register(cast("type[StrategyInterface]", NotAStrategy), _meta("bad"))


def test_suspended_strategy_cannot_execute() -> None:
    reg = SignalStrategyRegistry()
    reg.register(MomentumStrategy, _meta("susp"))
    reg.update_status("susp", StrategyStatus.SUSPENDED)
    with pytest.raises(RuntimeError, match="suspended"):
        reg.get_strategy("susp")


def test_base_interface_generate_signals_is_not_implemented() -> None:
    with pytest.raises(NotImplementedError):
        StrategyInterface().generate_signals(_price_frame())


def test_momentum_rejects_missing_close_column() -> None:
    with pytest.raises(ValueError, match="close"):
        MomentumStrategy().generate_signals(pd.DataFrame({"open": [1.0, 2.0]}))
