# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

# Re-export X-axis scoped isolation helpers so that the tree-wide
# conftest picks them up alongside the legacy shared fixtures.
from tests.fixtures.isolation import (  # noqa: F401 — fixture re-export
    isolated_env,
    isolated_modules,
)


@pytest.fixture(autouse=True)
def _set_seed():
    np.random.seed(42)
    yield
    np.random.seed(42)


@pytest.fixture
def sin_wave() -> np.ndarray:
    t = np.linspace(0, 4 * np.pi, 512, endpoint=False)
    return np.sin(t)


@pytest.fixture
def brownian_motion() -> np.ndarray:
    steps = np.random.normal(0, 1, size=4096)
    return np.cumsum(steps)


@pytest.fixture
def uniform_series() -> np.ndarray:
    return np.linspace(-1.0, 1.0, 300)


@pytest.fixture
def peaked_series() -> np.ndarray:
    data = np.zeros(200)
    data[:100] = -0.5
    data[100:] = 0.5
    return data


@pytest.fixture
def price_dataframe(tmp_path) -> pd.DataFrame:
    prices = np.linspace(100.0, 110.0, 50)
    df = pd.DataFrame({"price": prices})
    csv_path = tmp_path / "prices.csv"
    df.to_csv(csv_path, index=False)
    return pd.read_csv(csv_path)
