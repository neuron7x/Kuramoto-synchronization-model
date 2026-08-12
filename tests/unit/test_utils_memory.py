# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for the :mod:`core.utils.memory` module."""

from __future__ import annotations

import numpy as np
import pytest

from core.utils.memory import ArrayPool


def test_acquire_and_release_reuses_same_instance() -> None:
    pool = ArrayPool(dtype=np.float64)

    array = pool.acquire((2, 3))
    assert array.shape == (2, 3)
    assert array.dtype == np.float64

    pool.release(array)

    reused = pool.acquire((2, 3), dtype=np.float64)
    assert reused is array


def test_borrow_context_manager_returns_array_to_pool() -> None:
    pool = ArrayPool()

    with pool.borrow((4,), dtype=np.float32) as array:
        array.fill(42.0)
        borrowed_id = id(array)

    reused = pool.acquire((4,), dtype=np.float32)
    assert id(reused) == borrowed_id


def test_release_rejects_non_owning_views() -> None:
    pool = ArrayPool()

    original = pool.acquire((8,))
    view = original[:4]

    with pytest.raises(ValueError):
        pool.release(view)

    pool.release(original)
