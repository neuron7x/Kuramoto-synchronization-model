"""Ensure serotonin canonical modules are single-source with legacy mirrors."""


def test_serotonin_controller_mirror_aliases_canonical():
    from core.neuro.serotonin.serotonin_controller import (
        ControllerOutput as CanonControllerOutput,
        SerotoninConfig as CanonConfig,
        SerotoninConfigEnvelope as CanonEnvelope,
        SerotoninController as CanonController,
        SerotoninLegacyConfig as CanonLegacy,
    )
    from src.tradepulse.core.neuro.serotonin.serotonin_controller import (
        ControllerOutput as MirrorControllerOutput,
        SerotoninConfig as MirrorConfig,
        SerotoninConfigEnvelope as MirrorEnvelope,
        SerotoninController as MirrorController,
        SerotoninLegacyConfig as MirrorLegacy,
    )

    assert MirrorController is CanonController
    assert MirrorConfig is CanonConfig
    assert MirrorEnvelope is CanonEnvelope
    assert MirrorLegacy is CanonLegacy
    assert MirrorControllerOutput is CanonControllerOutput


def test_serotonin_observability_mirror_aliases_canonical():
    from core.neuro.serotonin.observability import (
        Alert as CanonAlert,
        AlertSeverity as CanonSeverity,
        SLI as CanonSLI,
        SLO as CanonSLO,
        SEROTONIN_ALERTS as CanonAlerts,
        SEROTONIN_SLIS as CanonSLIS,
        SEROTONIN_SLOS as CanonSLOS,
        SerotoninMonitor as CanonMonitor,
        create_grafana_dashboard_json as CanonGrafana,
        create_prometheus_metrics as CanonProm,
    )
    from src.tradepulse.core.neuro.serotonin.observability import (
        Alert as MirrorAlert,
        AlertSeverity as MirrorSeverity,
        SLI as MirrorSLI,
        SLO as MirrorSLO,
        SEROTONIN_ALERTS as MirrorAlerts,
        SEROTONIN_SLIS as MirrorSLIS,
        SEROTONIN_SLOS as MirrorSLOS,
        SerotoninMonitor as MirrorMonitor,
        create_grafana_dashboard_json as MirrorGrafana,
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
