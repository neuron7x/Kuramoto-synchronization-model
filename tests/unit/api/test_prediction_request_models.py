from __future__ import annotations

import os
from datetime import datetime

import pytest
from pydantic import ValidationError

# Prevent FastAPI application startup side-effects when importing models.
os.environ.setdefault("TRADEPULSE_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("TRADEPULSE_AUDIT_SECRET", "test-audit-secret")

from application.api.service import MarketBar, PredictionRequest


def _sample_bars() -> list[MarketBar]:
    return [
        MarketBar(
            timestamp=datetime(2024, 3, 1, 12, 0, 0),
            open=42000.0,
            high=42010.0,
            low=41980.0,
            close=42005.0,
            volume=18.5,
            bidVolume=9.2,
            askVolume=9.1,
            signedVolume=0.3,
        ),
        MarketBar(
            timestamp=datetime(2024, 3, 1, 12, 1, 0),
            open=42005.0,
            high=42015.0,
            low=41990.0,
            close=42008.0,
            volume=19.1,
            bidVolume=9.4,
            askVolume=9.2,
            signedVolume=-0.1,
        ),
    ]


def test_prediction_request_defaults_to_five_minute_horizon() -> None:
    request = PredictionRequest(symbol="BTC-USD", bars=_sample_bars())

    assert request.horizon_seconds == 300


@pytest.mark.parametrize("horizon", [60, 600, 3600])
def test_prediction_request_accepts_horizon_within_bounds(horizon: int) -> None:
    request = PredictionRequest(
        symbol="ETH-USD", bars=_sample_bars(), horizon_seconds=horizon
    )

    assert request.horizon_seconds == horizon


@pytest.mark.parametrize("horizon", [1, 30, 59, 3601, 7200])
def test_prediction_request_rejects_out_of_bounds_horizon(horizon: int) -> None:
    with pytest.raises(ValidationError):
        PredictionRequest(
            symbol="SOL-USD", bars=_sample_bars(), horizon_seconds=horizon
        )
