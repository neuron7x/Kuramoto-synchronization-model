from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

import numpy as np
from numpy.typing import NDArray

__version__: str
PYTHON_IMPLEMENTATION: str
PYTHON_VERSION: str

__all__ = [
    "sliding_windows",
    "quantiles",
    "convolve",
    "__version__",
    "PYTHON_IMPLEMENTATION",
    "PYTHON_VERSION",
]

def sliding_windows(data: NDArray[np.float64], window: int, step: int, /) -> NDArray[np.float64]:
    """Return flattened sliding windows as a 2D float64 NumPy array.

    Raises:
        ValueError: If ``window == 0`` or ``step == 0``, or if ``data`` is
            empty while ``window > 0`` (``NumericError::EmptyInput`` on the
            Rust side; surfaced as ``PyValueError``).
    """

def quantiles(data: NDArray[np.float64], probabilities: Sequence[float], /) -> NDArray[np.float64]:
    """Return linearly interpolated quantiles for sorted/unsorted input data.

    Raises:
        ValueError: If ``data`` is empty, or if any probability is NaN/Inf
            or outside ``[0, 1]``.
    """

def convolve(
    signal: NDArray[np.float64],
    kernel: NDArray[np.float64],
    mode: Literal["full", "same", "valid"],
    /,
) -> NDArray[np.float64]:
    """Convolve ``signal`` with ``kernel`` in ``full``, ``same``, or ``valid`` mode.

    Raises:
        ValueError: If ``signal`` or ``kernel`` is empty, or if ``mode`` is
            unsupported.
    """
