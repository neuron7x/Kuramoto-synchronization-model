# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""MFN stage numeric contract tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from geosync.mfn.contract import MFNContract
from geosync.mfn.pipeline import compare, detect, forecast, write_json


@pytest.mark.parametrize("value", ["missing", None, "not-a-number"])
def test_detect_rejects_bad_mean_return(tmp_path: Path, value: object) -> None:
    out = tmp_path / "bundle"
    features = {"volatility": 0.1}
    if value != "missing":
        features["mean_return"] = value
    write_json(
        out / "extract.json",
        {
            "schema_version": "mfn.integration.v1",
            "stage": "extract",
            "features": features,
        },
    )

    with pytest.raises(ValueError, match="mean_return"):
        detect(out, contract=MFNContract())


@pytest.mark.parametrize("value", ["missing", None, "not-a-number"])
def test_forecast_rejects_bad_last_price(tmp_path: Path, value: object) -> None:
    out = tmp_path / "bundle"
    features = {"mean_return": 0.1}
    if value != "missing":
        features["last_price"] = value
    write_json(
        out / "extract.json",
        {
            "schema_version": "mfn.integration.v1",
            "stage": "extract",
            "features": features,
        },
    )
    write_json(out / "detect.json", {"schema_version": "mfn.integration.v1", "stage": "detect"})

    with pytest.raises(ValueError, match="last_price"):
        forecast(out, contract=MFNContract())


@pytest.mark.parametrize("value", ["missing", None, "not-a-number"])
def test_compare_rejects_bad_last_price(tmp_path: Path, value: object) -> None:
    out = tmp_path / "bundle"
    features = {}
    if value != "missing":
        features["last_price"] = value
    write_json(
        out / "extract.json",
        {
            "schema_version": "mfn.integration.v1",
            "stage": "extract",
            "features": features,
        },
    )
    write_json(
        out / "forecast.json",
        {
            "schema_version": "mfn.integration.v1",
            "stage": "forecast",
            "predicted_next_price": 100.0,
        },
    )

    with pytest.raises(ValueError, match="last_price"):
        compare(out, contract=MFNContract())


@pytest.mark.parametrize("value", ["missing", None, "not-a-number"])
def test_compare_rejects_bad_prediction_value(tmp_path: Path, value: object) -> None:
    out = tmp_path / "bundle"
    write_json(
        out / "extract.json",
        {
            "schema_version": "mfn.integration.v1",
            "stage": "extract",
            "features": {"last_price": 100.0},
        },
    )
    forecast_payload = {"schema_version": "mfn.integration.v1", "stage": "forecast"}
    if value != "missing":
        forecast_payload["predicted_next_price"] = value
    write_json(out / "forecast.json", forecast_payload)

    with pytest.raises(ValueError, match="predicted_next_price"):
        compare(out, contract=MFNContract())
