"""Ensure serotonin canonical modules are single-source with legacy mirrors."""


def test_serotonin_controller_mirror_aliases_canonical():
    from core.neuro.serotonin.serotonin_controller import (
        ControllerOutput as CanonControllerOutput,
    )
    from core.neuro.serotonin.serotonin_controller import (
        SerotoninConfig as CanonConfig,
    )
    from core.neuro.serotonin.serotonin_controller import (
        SerotoninConfigEnvelope as CanonEnvelope,
    )
    from core.neuro.serotonin.serotonin_controller import (
        SerotoninController as CanonController,
    )
    from core.neuro.serotonin.serotonin_controller import (
        SerotoninLegacyConfig as CanonLegacy,
    )
    from core.neuro.serotonin.serotonin_controller import (
        _generate_config_table as CanonConfigTable,
    )
    from src.tradepulse.core.neuro.serotonin.serotonin_controller import (
        ControllerOutput as MirrorControllerOutput,
    )
    from src.tradepulse.core.neuro.serotonin.serotonin_controller import (
        SerotoninConfig as MirrorConfig,
    )
    from src.tradepulse.core.neuro.serotonin.serotonin_controller import (
        SerotoninConfigEnvelope as MirrorEnvelope,
    )
    from src.tradepulse.core.neuro.serotonin.serotonin_controller import (
        SerotoninController as MirrorController,
    )
    from src.tradepulse.core.neuro.serotonin.serotonin_controller import (
        SerotoninLegacyConfig as MirrorLegacy,
    )
    from src.tradepulse.core.neuro.serotonin.serotonin_controller import (
        _generate_config_table as MirrorConfigTable,
    )

    assert MirrorController is CanonController
    assert MirrorConfig is CanonConfig
    assert MirrorEnvelope is CanonEnvelope
    assert MirrorLegacy is CanonLegacy
    assert MirrorControllerOutput is CanonControllerOutput
    assert MirrorConfigTable is CanonConfigTable


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
    from src.tradepulse.core.neuro.serotonin.observability import (
        SEROTONIN_ALERTS as MirrorAlerts,
    )
    from src.tradepulse.core.neuro.serotonin.observability import (
        SEROTONIN_SLIS as MirrorSLIS,
    )
    from src.tradepulse.core.neuro.serotonin.observability import (
        SEROTONIN_SLOS as MirrorSLOS,
    )
    from src.tradepulse.core.neuro.serotonin.observability import (
        SLI as MirrorSLI,
    )
    from src.tradepulse.core.neuro.serotonin.observability import (
        SLO as MirrorSLO,
    )
    from src.tradepulse.core.neuro.serotonin.observability import (
        Alert as MirrorAlert,
    )
    from src.tradepulse.core.neuro.serotonin.observability import (
        AlertSeverity as MirrorSeverity,
    )
    from src.tradepulse.core.neuro.serotonin.observability import (
        SerotoninMonitor as MirrorMonitor,
    )
    from src.tradepulse.core.neuro.serotonin.observability import (
        create_grafana_dashboard_json as MirrorGrafana,
    )
    from src.tradepulse.core.neuro.serotonin.observability import (
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
