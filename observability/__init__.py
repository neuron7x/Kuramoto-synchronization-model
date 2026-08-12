# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Observability helpers for GeoSync.

Loading is lazy (PEP 562). Importing a light submodule such as
``observability.tracing`` (used by ``core.indicators.base``) must NOT eagerly
drag in heavy peers like ``release_gates`` → ``execution`` → ``pydantic`` or
``notifications`` → ``httpx``. Names below resolve to their submodule on first
attribute access; ``from observability import X`` keeps working unchanged.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

# attribute name -> submodule (relative, without leading dot)
_EXPORTS: dict[str, str] = {
    # auto_triage
    "AutoTriageConfig": "auto_triage",
    "AutoTriageOrchestrator": "auto_triage",
    "AutoTriageReport": "auto_triage",
    "MetricThreshold": "auto_triage",
    "TriageStepReport": "auto_triage",
    # bootstrap
    "AlertNoiseGuard": "bootstrap",
    "EndpointCheck": "bootstrap",
    "EndpointCheckResult": "bootstrap",
    "EndpointValidator": "bootstrap",
    "ExporterSetup": "bootstrap",
    "LoggingSetup": "bootstrap",
    "MetricsSetup": "bootstrap",
    "MetricsValidationIssue": "bootstrap",
    "MetricsValidationReport": "bootstrap",
    "ObservabilityBootstrapper": "bootstrap",
    "PostmortemTemplateBuilder": "bootstrap",
    "SLOPolicy": "bootstrap",
    "SLOSuite": "bootstrap",
    "SyntheticCheck": "bootstrap",
    "SyntheticSuite": "bootstrap",
    "TracingSetup": "bootstrap",
    "build_default_bootstrapper": "bootstrap",
    # cache_warmup
    "CacheUsageStats": "cache_warmup",
    "CacheWarmupController": "cache_warmup",
    "CacheWarmupResult": "cache_warmup",
    "CacheWarmupSpec": "cache_warmup",
    "CacheWarmupStatus": "cache_warmup",
    # drift
    "DriftAlert": "drift",
    "DriftDashboard": "drift",
    "DriftDetector": "drift",
    "DriftMonitoringReport": "drift",
    "DriftMonitoringService": "drift",
    "FeatureChangeLog": "drift",
    "FeatureChangeRecord": "drift",
    "FeatureDriftMetric": "drift",
    "FeatureDriftSummary": "drift",
    "FeatureSnapshot": "drift",
    "ImpactIsolationPlanner": "drift",
    "IsolationDecision": "drift",
    "IsolationPlan": "drift",
    "QualityDegradationMonitor": "drift",
    "QualityDeviation": "drift",
    "QualityGuardrail": "drift",
    "RemediationAction": "drift",
    "RemediationPlan": "drift",
    "RemediationPlanner": "drift",
    "RetrainingDecision": "drift",
    "RetrainingTrigger": "drift",
    # finops
    "AlertSink": "finops",
    "Budget": "finops",
    "BudgetStatus": "finops",
    "CostOptimisationPlan": "finops",
    "CostReport": "finops",
    "FinOpsAlert": "finops",
    "FinOpsController": "finops",
    "NotificationAlertSink": "finops",
    "OptimizationRecommendation": "finops",
    "ResourceProfile": "finops",
    "ResourceUsageSample": "finops",
    # health
    "HealthServer": "health",
    # incidents
    "IncidentManager": "incidents",
    "IncidentRecord": "incidents",
    # logging
    "StructuredLogFormatter": "logging",
    "configure_logging": "logging",
    # model_monitoring
    "DegradationSignal": "model_monitoring",
    "EventLabel": "model_monitoring",
    "InferenceContext": "model_monitoring",
    "ModelObservabilityConfig": "model_monitoring",
    "ModelObservabilityOrchestrator": "model_monitoring",
    "PostmortemTemplate": "model_monitoring",
    "QualityBaseline": "model_monitoring",
    "QualityConfidenceInterval": "model_monitoring",
    "ResourceSnapshot": "model_monitoring",
    # notifications
    "EmailSender": "notifications",
    "NotificationDispatcher": "notifications",
    "SlackNotifier": "notifications",
    "TeamsNotifier": "notifications",
    # profiling
    "ProfileCollector": "profiling",
    "ProfileReport": "profiling",
    "ProfileSectionResult": "profiling",
    # release_gates
    "ReleaseGateEvaluator": "release_gates",
    "ReleaseGateResult": "release_gates",
    # response_quality
    "ActiveSample": "response_quality",
    "ComplaintRecord": "response_quality",
    "DatasetBaseline": "response_quality",
    "GoldenDataset": "response_quality",
    "GoldenRecord": "response_quality",
    "ImprovementLog": "response_quality",
    "QualityContract": "response_quality",
    "QualityContractViolation": "response_quality",
    "QualityFailure": "response_quality",
    "QualityRunSummary": "response_quality",
    "ResponseQualityConfig": "response_quality",
    "ResponseQualityOrchestrator": "response_quality",
    "ReviewTicket": "response_quality",
    # tracing
    "TracingConfig": "tracing",
    "activate_traceparent": "tracing",
    "configure_tracing": "tracing",
    "current_traceparent": "tracing",
    "extract_trace_context": "tracing",
    "get_tracer": "tracing",
    "inject_trace_context": "tracing",
    "pipeline_span": "tracing",
}

# attribute name -> (submodule, original attribute name) for renamed re-exports
_ALIASES: dict[str, tuple[str, str]] = {
    "AutoTriageDetectionResult": ("auto_triage", "DetectionResult"),
}

__all__ = list(_EXPORTS) + list(_ALIASES)


def __getattr__(name: str) -> Any:
    alias = _ALIASES.get(name)
    if alias is not None:
        module_name, attr = alias
    else:
        module_name = _EXPORTS.get(name)  # type: ignore[assignment]
        if module_name is None:
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
        attr = name
    module = import_module(f".{module_name}", __name__)
    value = getattr(module, attr)
    globals()[name] = value  # cache so subsequent access skips __getattr__
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))


if TYPE_CHECKING:  # eager names for static analysers / IDEs only.
    # Redundant ``as`` aliases mark these as intentional re-exports (ruff/mypy).
    from .auto_triage import AutoTriageConfig as AutoTriageConfig
    from .auto_triage import AutoTriageOrchestrator as AutoTriageOrchestrator
    from .auto_triage import AutoTriageReport as AutoTriageReport
    from .auto_triage import DetectionResult as AutoTriageDetectionResult  # noqa: F401
    from .auto_triage import MetricThreshold as MetricThreshold
    from .auto_triage import TriageStepReport as TriageStepReport
    from .bootstrap import AlertNoiseGuard as AlertNoiseGuard
    from .bootstrap import EndpointCheck as EndpointCheck
    from .bootstrap import EndpointCheckResult as EndpointCheckResult
    from .bootstrap import EndpointValidator as EndpointValidator
    from .bootstrap import ExporterSetup as ExporterSetup
    from .bootstrap import LoggingSetup as LoggingSetup
    from .bootstrap import MetricsSetup as MetricsSetup
    from .bootstrap import MetricsValidationIssue as MetricsValidationIssue
    from .bootstrap import MetricsValidationReport as MetricsValidationReport
    from .bootstrap import ObservabilityBootstrapper as ObservabilityBootstrapper
    from .bootstrap import PostmortemTemplateBuilder as PostmortemTemplateBuilder
    from .bootstrap import SLOPolicy as SLOPolicy
    from .bootstrap import SLOSuite as SLOSuite
    from .bootstrap import SyntheticCheck as SyntheticCheck
    from .bootstrap import SyntheticSuite as SyntheticSuite
    from .bootstrap import TracingSetup as TracingSetup
    from .bootstrap import build_default_bootstrapper as build_default_bootstrapper
    from .cache_warmup import CacheUsageStats as CacheUsageStats
    from .cache_warmup import CacheWarmupController as CacheWarmupController
    from .cache_warmup import CacheWarmupResult as CacheWarmupResult
    from .cache_warmup import CacheWarmupSpec as CacheWarmupSpec
    from .cache_warmup import CacheWarmupStatus as CacheWarmupStatus
    from .drift import DriftAlert as DriftAlert
    from .drift import DriftDashboard as DriftDashboard
    from .drift import DriftDetector as DriftDetector
    from .drift import DriftMonitoringReport as DriftMonitoringReport
    from .drift import DriftMonitoringService as DriftMonitoringService
    from .drift import FeatureChangeLog as FeatureChangeLog
    from .drift import FeatureChangeRecord as FeatureChangeRecord
    from .drift import FeatureDriftMetric as FeatureDriftMetric
    from .drift import FeatureDriftSummary as FeatureDriftSummary
    from .drift import FeatureSnapshot as FeatureSnapshot
    from .drift import ImpactIsolationPlanner as ImpactIsolationPlanner
    from .drift import IsolationDecision as IsolationDecision
    from .drift import IsolationPlan as IsolationPlan
    from .drift import QualityDegradationMonitor as QualityDegradationMonitor
    from .drift import QualityDeviation as QualityDeviation
    from .drift import QualityGuardrail as QualityGuardrail
    from .drift import RemediationAction as RemediationAction
    from .drift import RemediationPlan as RemediationPlan
    from .drift import RemediationPlanner as RemediationPlanner
    from .drift import RetrainingDecision as RetrainingDecision
    from .drift import RetrainingTrigger as RetrainingTrigger
    from .finops import AlertSink as AlertSink
    from .finops import Budget as Budget
    from .finops import BudgetStatus as BudgetStatus
    from .finops import CostOptimisationPlan as CostOptimisationPlan
    from .finops import CostReport as CostReport
    from .finops import FinOpsAlert as FinOpsAlert
    from .finops import FinOpsController as FinOpsController
    from .finops import NotificationAlertSink as NotificationAlertSink
    from .finops import OptimizationRecommendation as OptimizationRecommendation
    from .finops import ResourceProfile as ResourceProfile
    from .finops import ResourceUsageSample as ResourceUsageSample
    from .health import HealthServer as HealthServer
    from .incidents import IncidentManager as IncidentManager
    from .incidents import IncidentRecord as IncidentRecord
    from .logging import StructuredLogFormatter as StructuredLogFormatter
    from .logging import configure_logging as configure_logging
    from .model_monitoring import DegradationSignal as DegradationSignal
    from .model_monitoring import EventLabel as EventLabel
    from .model_monitoring import InferenceContext as InferenceContext
    from .model_monitoring import ModelObservabilityConfig as ModelObservabilityConfig
    from .model_monitoring import ModelObservabilityOrchestrator as ModelObservabilityOrchestrator
    from .model_monitoring import PostmortemTemplate as PostmortemTemplate
    from .model_monitoring import QualityBaseline as QualityBaseline
    from .model_monitoring import QualityConfidenceInterval as QualityConfidenceInterval
    from .model_monitoring import ResourceSnapshot as ResourceSnapshot
    from .notifications import EmailSender as EmailSender
    from .notifications import NotificationDispatcher as NotificationDispatcher
    from .notifications import SlackNotifier as SlackNotifier
    from .notifications import TeamsNotifier as TeamsNotifier
    from .profiling import ProfileCollector as ProfileCollector
    from .profiling import ProfileReport as ProfileReport
    from .profiling import ProfileSectionResult as ProfileSectionResult
    from .release_gates import ReleaseGateEvaluator as ReleaseGateEvaluator
    from .release_gates import ReleaseGateResult as ReleaseGateResult
    from .response_quality import ActiveSample as ActiveSample
    from .response_quality import ComplaintRecord as ComplaintRecord
    from .response_quality import DatasetBaseline as DatasetBaseline
    from .response_quality import GoldenDataset as GoldenDataset
    from .response_quality import GoldenRecord as GoldenRecord
    from .response_quality import ImprovementLog as ImprovementLog
    from .response_quality import QualityContract as QualityContract
    from .response_quality import QualityContractViolation as QualityContractViolation
    from .response_quality import QualityFailure as QualityFailure
    from .response_quality import QualityRunSummary as QualityRunSummary
    from .response_quality import ResponseQualityConfig as ResponseQualityConfig
    from .response_quality import ResponseQualityOrchestrator as ResponseQualityOrchestrator
    from .response_quality import ReviewTicket as ReviewTicket
    from .tracing import TracingConfig as TracingConfig
    from .tracing import activate_traceparent as activate_traceparent
    from .tracing import configure_tracing as configure_tracing
    from .tracing import current_traceparent as current_traceparent
    from .tracing import extract_trace_context as extract_trace_context
    from .tracing import get_tracer as get_tracer
    from .tracing import inject_trace_context as inject_trace_context
    from .tracing import pipeline_span as pipeline_span
