# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Callable, Dict, Mapping

import pytest
import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from nak_controller.core.config import NakConfig
from nak_controller.core.metrics import (
    dd_norm,
    lat_norm,
    pnl_norm,
    slippage_norm,
    vol_norm,
)
from nak_controller.runtime.controller import NaKController

CONFIG_PATH = Path("nak_controller/conf/nak.yaml")
RAW_CONFIG: Dict[str, Any] = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))["nak"]


def _make_config(**overrides: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = copy.deepcopy(RAW_CONFIG)
    for key, value in overrides.items():
        data[key] = value
    return data


def test_controller_requires_nak_root(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("other: {}\n", encoding="utf-8")
    with pytest.raises(KeyError):
        NaKController(path)


def test_configuration_rejects_unknown_field(tmp_path: Path) -> None:
    path = tmp_path / "invalid.yaml"
    payload = copy.deepcopy(RAW_CONFIG)
    payload["unexpected_field"] = True
    path.write_text(yaml.safe_dump({"nak": payload}), encoding="utf-8")
    with pytest.raises(ValidationError):
        NaKController(path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("L_max", 0.0),
        ("E_max", 0.0),
        ("EI_high", 0.2),
        ("EI_hysteresis", -0.01),
        ("r_min", 0.0),
        ("I_max", 0.0),
        ("delta_r_limit", 0.0),
        ("delta_r_limit", 1.5),
        ("vol_red", 0.6),
        ("dd_red", 0.3),
        ("noise_sigma", -0.001),
    ],
)
def test_scalar_field_validations(field: str, value: float) -> None:
    config = _make_config(**{field: value})
    with pytest.raises(ValidationError):
        NakConfig(**config)


def test_weight_sum_must_not_exceed_one() -> None:
    config = _make_config(w_n=0.3, w_v=0.3, w_d=0.3, w_e=0.2, w_l=0.1, w_s=0.1)
    with pytest.raises(ValidationError):
        NakConfig(**config)


def test_recovery_reserve_must_be_positive() -> None:
    config = _make_config(u_e=0.0, u_l=0.0, u_p=0.0)
    with pytest.raises(ValidationError):
        NakConfig(**config)


def test_risk_and_frequency_bounds_validate_ordering() -> None:
    config = _make_config(r_min=0.8, r_max=0.7)
    with pytest.raises(ValidationError):
        NakConfig(**config)
    config = _make_config(f_min=1.6, f_max=1.5)
    with pytest.raises(ValidationError):
        NakConfig(**config)


def test_risk_range_must_include_unity() -> None:
    config = _make_config(r_min=0.1, r_max=0.9)
    with pytest.raises(ValidationError):
        NakConfig(**config)


MetricFunc = Callable[[float], float]


@pytest.mark.parametrize(
    ("func", "value", "expected"),
    [
        (pnl_norm, 0.0, 0.5),
        (pnl_norm, 0.02, 1.0),
        (pnl_norm, -0.02, 0.0),
        (dd_norm, 0.1, 0.5),
        (vol_norm, 0.8, 0.8),
        (lat_norm, 25.0, 0.5),
        (slippage_norm, -0.0005, 0.5),
    ],
)
def test_metric_normalizations(func: MetricFunc, value: float, expected: float) -> None:
    assert func(value) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("func", "kwargs"),
    [
        (pnl_norm, {"pnl": 0.0, "scale": 0.0}),
        (dd_norm, {"drawdown": 0.1, "max_dd": 0.0}),
        (vol_norm, {"volatility": 0.1, "max_vol": 0.0}),
        (lat_norm, {"latency_ms": 10.0, "p95_ms": 0.0}),
        (slippage_norm, {"slippage": 0.0, "threshold": 0.0}),
    ],
)
def test_metric_validations(func: Callable[..., float], kwargs: Mapping[str, float]) -> None:
    with pytest.raises(ValueError):
        func(**kwargs)
