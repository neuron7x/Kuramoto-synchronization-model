# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Legacy mirror for serotonin API; canonical lives in core.neuro.serotonin.*"""

__CANONICAL__ = True

from geosync.core.neuro.serotonin.observability import (
    SEROTONIN_ALERTS,
    SEROTONIN_SLIS,
    SEROTONIN_SLOS,
    SLI,
    SLO,
    Alert,
    AlertSeverity,
    SerotoninMonitor,
    create_grafana_dashboard_json,
    create_prometheus_metrics,
)
from geosync.core.neuro.serotonin.serotonin_controller import (
    ControllerOutput,
    SerotoninConfig,
    SerotoninConfigEnvelope,
    SerotoninController,
    SerotoninLegacyConfig,
    _generate_config_table,
)

__all__ = [
    "Alert",
    "AlertSeverity",
    "ControllerOutput",
    "SerotoninConfig",
    "SerotoninConfigEnvelope",
    "SerotoninController",
    "SerotoninLegacyConfig",
    "SerotoninMonitor",
    "SLI",
    "SLO",
    "SEROTONIN_ALERTS",
    "SEROTONIN_SLIS",
    "SEROTONIN_SLOS",
    "_generate_config_table",
    "create_grafana_dashboard_json",
    "create_prometheus_metrics",
]
