# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import numpy as np
import pytest

from analytics.regime.src.core.ricci_flow import _project_simplex


def test_project_simplex_respects_lower_bound():
    vector = np.array([0.9, 0.05, 0.05])
    projected = _project_simplex(vector, lower_bound=0.1)

    assert np.isclose(projected.sum(), 1.0)
    assert projected.min() >= 0.1 - 1e-12


def test_project_simplex_handles_uniform_floor():
    projected = _project_simplex([0.0, 0.0, 0.0], lower_bound=1.0 / 3.0)

    assert np.allclose(projected, np.repeat(1.0 / 3.0, 3))


@pytest.mark.parametrize("lower_bound", [0.6, 1.0])
def test_project_simplex_invalid_lower_bound(lower_bound):
    with pytest.raises(ValueError):
        _project_simplex([0.2, 0.5, 0.3], lower_bound=lower_bound)
