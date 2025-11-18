from __future__ import annotations

import importlib
import sys


def test_numeric_module_imports_without_numpy() -> None:
    """Ensure numeric accelerators gracefully degrade when numpy is absent."""

    original_numpy = sys.modules.get("numpy")
    # Remove any previously loaded numeric module so the import reflects the missing numpy state.
    sys.modules.pop("core.accelerators.numeric", None)
    sys.modules["numpy"] = None  # type: ignore[assignment]

    try:
        numeric = importlib.import_module("core.accelerators.numeric")
        assert not numeric._NUMPY_AVAILABLE
        assert not numeric._RUST_ACCEL_AVAILABLE

        windows = numeric.sliding_windows([1, 2, 3, 4], window=2, step=1, use_rust=False)
        assert windows == [[1.0, 2.0], [2.0, 3.0], [3.0, 4.0]]

        quantile_values = numeric.quantiles([1, 2, 3, 4], [0.25, 0.5, 0.75], use_rust=False)
        assert quantile_values == [1.75, 2.5, 3.25]

        convolution = numeric.convolve([1, 2, 3], [1, 1], mode="valid", use_rust=False)
        assert convolution == [3.0, 5.0]
    finally:
        if original_numpy is not None:
            sys.modules["numpy"] = original_numpy
        else:
            sys.modules.pop("numpy", None)
        sys.modules.pop("core.accelerators.numeric", None)
        importlib.import_module("core.accelerators.numeric")
