# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Ensure serotonin canonical modules are single-source with legacy mirrors."""


def test_serotonin_controller_mirror_aliases_canonical():
    from core.neuro.serotonin.serotonin_controller import (
        ControllerOutput as ShimControllerOutput,
    )
    from core.neuro.serotonin.serotonin_controller import (
        SerotoninConfig as ShimConfig,
    )
    from core.neuro.serotonin.serotonin_controller import (
        SerotoninConfigEnvelope as ShimEnvelope,
    )
    from core.neuro.serotonin.serotonin_controller import (
        SerotoninController as ShimController,
    )
    from core.neuro.serotonin.serotonin_controller import (
        SerotoninLegacyConfig as ShimLegacy,
    )
    from core.neuro.serotonin.serotonin_controller import (
        _generate_config_table as ShimConfigTable,
    )
    from geosync.core.neuro.serotonin.serotonin_controller import (
        ControllerOutput as CanonControllerOutput,
    )
    from geosync.core.neuro.serotonin.serotonin_controller import (
        SerotoninConfig as CanonConfig,
    )
    from geosync.core.neuro.serotonin.serotonin_controller import (
        SerotoninConfigEnvelope as CanonEnvelope,
    )
    from geosync.core.neuro.serotonin.serotonin_controller import (
        SerotoninController as CanonController,
    )
    from geosync.core.neuro.serotonin.serotonin_controller import (
        SerotoninLegacyConfig as CanonLegacy,
    )
    from geosync.core.neuro.serotonin.serotonin_controller import (
        _generate_config_table as CanonConfigTable,
    )

    assert ShimController is CanonController
    assert ShimConfig is CanonConfig
    assert ShimEnvelope is CanonEnvelope
    assert ShimLegacy is CanonLegacy
    assert ShimControllerOutput is CanonControllerOutput
    assert ShimConfigTable is CanonConfigTable

    import core.neuro.serotonin.serotonin_controller as shim_module
    import geosync.core.neuro.serotonin.serotonin_controller as canonical_module

    assert getattr(canonical_module, "__CANONICAL__")
    assert getattr(shim_module, "__CANONICAL__") is False


def test_serotonin_observability_mirror_aliases_canonical():
    from core.neuro.serotonin.observability import (
        SEROTONIN_ALERTS as CanonAlerts,
    )
    from core.neuro.serotonin.observability import (
        SEROTONIN_SLIS as CanonSLIS,
    )
    from core.neuro.serotonin.observability import (
        SEROTONIN_SLOS as CanonSLOS,
    )
    from core.neuro.serotonin.observability import (
        SLI as CanonSLI,
    )
    from core.neuro.serotonin.observability import (
        SLO as CanonSLO,
    )
    from core.neuro.serotonin.observability import (
        Alert as CanonAlert,
    )
    from core.neuro.serotonin.observability import (
        AlertSeverity as CanonSeverity,
    )
    from core.neuro.serotonin.observability import (
        SerotoninMonitor as CanonMonitor,
    )
    from core.neuro.serotonin.observability import (
        create_grafana_dashboard_json as CanonGrafana,
    )
    from core.neuro.serotonin.observability import (
        create_prometheus_metrics as CanonProm,
    )
    from src.geosync.core.neuro.serotonin.observability import (
        SEROTONIN_ALERTS as MirrorAlerts,
    )
    from src.geosync.core.neuro.serotonin.observability import (
        SEROTONIN_SLIS as MirrorSLIS,
    )
    from src.geosync.core.neuro.serotonin.observability import (
        SEROTONIN_SLOS as MirrorSLOS,
    )
    from src.geosync.core.neuro.serotonin.observability import (
        SLI as MirrorSLI,
    )
    from src.geosync.core.neuro.serotonin.observability import (
        SLO as MirrorSLO,
    )
    from src.geosync.core.neuro.serotonin.observability import (
        Alert as MirrorAlert,
    )
    from src.geosync.core.neuro.serotonin.observability import (
        AlertSeverity as MirrorSeverity,
    )
    from src.geosync.core.neuro.serotonin.observability import (
        SerotoninMonitor as MirrorMonitor,
    )
    from src.geosync.core.neuro.serotonin.observability import (
        create_grafana_dashboard_json as MirrorGrafana,
    )
    from src.geosync.core.neuro.serotonin.observability import (
        create_prometheus_metrics as MirrorProm,
    )

    assert MirrorAlert is CanonAlert
    assert MirrorSeverity is CanonSeverity
    assert MirrorSLI is CanonSLI
    assert MirrorSLO is CanonSLO
    assert MirrorAlerts is CanonAlerts
    assert MirrorSLIS is CanonSLIS
    assert MirrorSLOS is CanonSLOS
    assert MirrorMonitor is CanonMonitor
    assert MirrorGrafana is CanonGrafana
    assert MirrorProm is CanonProm
