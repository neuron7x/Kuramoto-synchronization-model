import pandas as pd
import pytest

from tradepulse.features.causal import CausalGuard


def test_non_numeric_drivers_are_skipped():
    df = pd.DataFrame(
        {
            "target": list(range(1, 16)),
            "driver_str": ["a"] * 15,
        }
    )

    guard = CausalGuard(max_lag=2)

    result = guard.fit_transform(df, target="target")

    assert result == {"TE_pass": False}


def test_non_numeric_target_raises():
    df = pd.DataFrame(
        {
            "target": ["a"] * 9,
            "driver": list(range(1, 10)),
        }
    )
    guard = CausalGuard(max_lag=2)

    with pytest.raises(ValueError):
        guard.fit_transform(df, target="target")
