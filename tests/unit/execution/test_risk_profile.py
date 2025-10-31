from __future__ import annotations

from pathlib import Path

import pytest

from execution.risk.profile import (
    clear_risk_profile_cache,
    load_risk_profile,
    resolve_risk_profile_path,
)


def test_load_risk_profile_uses_repository_defaults() -> None:
    clear_risk_profile_cache()
    profile = load_risk_profile(force_reload=True)

    limits = profile.build_risk_limits()
    assert limits.max_position == pytest.approx(10.0)
    assert profile.max_leverage == pytest.approx(5.0)
    assert profile.active_mode == "paper"


def test_load_risk_profile_supports_overrides(tmp_path: Path) -> None:
    payload = """
name = "custom"
[modes]
default = "live"
allowed = ["live", "paper"]

[limits]
max_notional = 2000.0
max_position = 2.5
max_leverage = 3.0
max_orders_per_interval = 10
interval_seconds = 0.5

[limits.kill_switch]
limit_multiplier = 1.2
violation_threshold = 2
rate_limit_threshold = 4

[permissions]
allowed_instruments = ["BTC-USDT", "BTC-USDT", ""]
"""
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(payload, encoding="utf-8")

    clear_risk_profile_cache()
    profile = load_risk_profile(profile_path, mode="paper", force_reload=True)

    assert profile.active_mode == "paper"
    assert profile.allowed_modes == ("live", "paper")
    assert profile.allowed_instruments == ("BTC-USDT",)

    limits = profile.build_risk_limits()
    assert limits.max_position == pytest.approx(2.5)
    assert limits.max_orders_per_interval == 10
    assert limits.kill_switch_violation_threshold == 2

    resolved = resolve_risk_profile_path(profile_path)
    assert resolved == profile_path.resolve()
