import numpy as np
import pytest

from core.metrics import (
    mean_absolute_error,
    mean_absolute_percentage_error,
    mean_squared_error,
    r2_score,
    root_mean_squared_error,
    symmetric_mean_absolute_percentage_error,
)


def test_regression_metrics_match_numpy() -> None:
    y_true = np.array([1.0, 2.0, 3.0, 4.0])
    y_pred = np.array([0.8, 2.5, 2.9, 3.7])

    mae = mean_absolute_error(y_true, y_pred)
    mse = mean_squared_error(y_true, y_pred)
    rmse = root_mean_squared_error(y_true, y_pred)
    mape_value = mean_absolute_percentage_error(y_true, y_pred)
    smape = symmetric_mean_absolute_percentage_error(y_true, y_pred)
    r2 = r2_score(y_true, y_pred)

    np.testing.assert_allclose(mae, np.mean(np.abs(y_true - y_pred)))
    np.testing.assert_allclose(mse, np.mean((y_true - y_pred) ** 2))
    np.testing.assert_allclose(rmse, np.sqrt(np.mean((y_true - y_pred) ** 2)))
    np.testing.assert_allclose(mape_value, np.mean(np.abs((y_true - y_pred) / y_true)))

    denom = np.maximum(np.abs(y_true) + np.abs(y_pred), 1e-8)
    expected_smape = np.mean(np.abs(y_true - y_pred) / denom) * 2.0
    np.testing.assert_allclose(smape, expected_smape)

    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    ss_res = np.sum((y_true - y_pred) ** 2)
    np.testing.assert_allclose(r2, 1.0 - ss_res / ss_tot)


def test_regression_metrics_validate_shapes() -> None:
    with pytest.raises(ValueError):
        mean_absolute_error([1.0, 2.0], [1.0])


def test_r2_score_handles_constant_series() -> None:
    assert r2_score([5.0, 5.0, 5.0], [5.0, 5.0, 5.0]) == 1.0
    assert r2_score([5.0, 5.0, 5.0], [5.5, 5.5, 5.5]) == 0.0
