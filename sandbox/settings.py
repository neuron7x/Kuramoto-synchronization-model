# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Environment-aware settings for sandbox services."""

from __future__ import annotations

from functools import lru_cache
from typing import Dict

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MarketSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SANDBOX_MARKET_", extra="ignore")
    symbols: tuple[str, ...] = Field(default=("btcusd", "ethusd", "solusd"))
    price_window: int = Field(default=48, ge=5, le=512)


class ServiceEndpoints(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SANDBOX_", extra="ignore")
    market_url: AnyHttpUrl = Field(default="http://mock-market:8000")
    signal_url: AnyHttpUrl = Field(default="http://signal-core:8001")
    risk_url: AnyHttpUrl = Field(default="http://risk-engine:8002")
    execution_url: AnyHttpUrl = Field(default="http://execution-paper:8003")
    control_url: AnyHttpUrl = Field(default="http://control-api:8004")


class SignalSettings(ServiceEndpoints):
    model_config = SettingsConfigDict(env_prefix="SANDBOX_SIGNAL_", extra="ignore")
    analysis_window: int = Field(default=48, ge=5, le=512)
    sensitivity: float = Field(default=0.004, ge=0.0, le=0.2)


class RiskSettings(ServiceEndpoints):
    model_config = SettingsConfigDict(env_prefix="SANDBOX_RISK_", extra="ignore")
    max_position: float = Field(default=25.0, gt=0.0)
    max_notional: float = Field(default=250_000.0, gt=0.0)


class ExecutionSettings(ServiceEndpoints):
    model_config = SettingsConfigDict(env_prefix="SANDBOX_EXECUTION_", extra="ignore")
    slippage_bps: float = Field(default=3.0, ge=0.0, le=50.0)


class ControlSettings(ServiceEndpoints):
    model_config = SettingsConfigDict(env_prefix="SANDBOX_CONTROL_", extra="ignore")
    health_targets: Dict[str, AnyHttpUrl] = Field(  # type: ignore[assignment]
        default={
            "mock-market": "http://mock-market:8000/health",
            "signal-core": "http://signal-core:8001/health",
            "risk-engine": "http://risk-engine:8002/health",
            "execution-paper": "http://execution-paper:8003/health",
        }
    )


@lru_cache
def market_settings() -> MarketSettings:
    return MarketSettings()  # type: ignore[call-arg]


@lru_cache
def signal_settings() -> SignalSettings:
    return SignalSettings()  # type: ignore[call-arg]


@lru_cache
def risk_settings() -> RiskSettings:
    return RiskSettings()  # type: ignore[call-arg]


@lru_cache
def execution_settings() -> ExecutionSettings:
    return ExecutionSettings()  # type: ignore[call-arg]


@lru_cache
def control_settings() -> ControlSettings:
    return ControlSettings()  # type: ignore[call-arg]
