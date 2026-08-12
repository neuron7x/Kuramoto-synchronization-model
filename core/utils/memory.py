# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Lightweight memory pooling utilities used by performance critical paths."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from contextlib import contextmanager
from typing import Iterator, MutableMapping

import numpy as np


class ArrayPool:
    """Reusable pool of NumPy arrays for zero-copy indicator pipelines."""

    def __init__(self, dtype: np.dtype | str = np.float32) -> None:
        self.dtype = np.dtype(dtype)
        self._pool: MutableMapping[tuple[tuple[int, ...], np.dtype], list[np.ndarray]] = (
            defaultdict(list)
        )

    def acquire(self, shape: Iterable[int], *, dtype: np.dtype | str | None = None) -> np.ndarray:
        requested_dtype = np.dtype(dtype) if dtype is not None else self.dtype
        key = (tuple(int(s) for s in shape), requested_dtype)
        bucket = self._pool.get(key)
        if bucket:
            return bucket.pop()
        return np.empty(key[0], dtype=requested_dtype)

    def release(self, array: np.ndarray) -> None:
        if not isinstance(array, np.ndarray):  # pragma: no cover - defensive
            raise TypeError("ArrayPool.release expects a numpy.ndarray")

        if not array.flags.c_contiguous:
            raise ValueError("Only contiguous arrays can be released back to the pool")

        if not array.flags.owndata:
            raise ValueError("Cannot release views that do not own their memory")

        key = (tuple(int(s) for s in array.shape), array.dtype)
        self._pool[key].append(array)

    def clear(self) -> None:
        self._pool.clear()

    @contextmanager
    def borrow(
        self,
        shape: Iterable[int],
        *,
        dtype: np.dtype | str | None = None,
    ) -> Iterator[np.ndarray]:
        """Context manager that automatically returns arrays to the pool."""

        array = self.acquire(shape, dtype=dtype)

        try:
            yield array
        finally:
            self.release(array)


__all__ = ["ArrayPool"]
