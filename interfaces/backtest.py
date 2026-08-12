# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Interfaces describing backtest orchestration contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Generic, TypeVar

import numpy as np
from numpy.typing import NDArray

ResultT = TypeVar("ResultT")


class BacktestEngine(ABC, Generic[ResultT]):
    """Generic contract for executing backtests."""

    @abstractmethod
    def run(
        self,
        prices: NDArray[np.float64],
        signal_fn: Callable[[NDArray[np.float64]], NDArray[np.float64]],
        *,
        fee: float = 0.0005,
        initial_capital: float = 0.0,
        strategy_name: str = "default",
        **kwargs,
    ) -> ResultT:
        """Execute the backtest and return the resulting analytics."""
