# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for loading module configuration files."""

import json

from modules.config import load_modules_config


def test_load_modules_config_from_json(tmp_path):
    payload = {
        "adaptive_risk_manager": {
            "risk_tolerance": 0.05,
            "var_window": 150,
            "volatility_window": 25,
        },
        "market_regime_analyzer": {
            "regime_window": 120,
            "transition_threshold": 0.65,
        },
        "execution_analyzer": {
            "slippage_threshold_bps": 7.5,
            "latency_threshold_ms": 250.0,
        },
        "alert_manager": {
            "deduplication_window_seconds": 200,
            "max_history_size": 500,
            "enable_aggregation": False,
        },
        "system_health_dashboard": {
            "check_interval_seconds": 12.0,
            "unhealthy_threshold_errors": 4,
            "degraded_threshold_latency_ms": 750.0,
        },
    }

    path = tmp_path / "module_config.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    config = load_modules_config(path)

    assert config.adaptive_risk_manager.risk_tolerance == 0.05
    assert config.adaptive_risk_manager.var_window == 150
    assert config.adaptive_risk_manager.volatility_window == 25
    assert config.market_regime_analyzer.regime_window == 120
    assert config.market_regime_analyzer.transition_threshold == 0.65
    assert config.execution_analyzer.slippage_threshold_bps == 7.5
    assert config.execution_analyzer.latency_threshold_ms == 250.0
    assert config.alert_manager.deduplication_window_seconds == 200
    assert config.alert_manager.max_history_size == 500
    assert config.alert_manager.enable_aggregation is False
    assert config.system_health_dashboard.check_interval_seconds == 12.0
    assert config.system_health_dashboard.unhealthy_threshold_errors == 4
    assert config.system_health_dashboard.degraded_threshold_latency_ms == 750.0
