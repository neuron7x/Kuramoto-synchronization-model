"""High-level platform assembly helpers."""

from .api_messaging_integration import (
    GatewayRequest,
    IntegrationRoute,
    IntegrationRouteConflictError,
    IntegrationRouteError,
    IntegrationRouteNotFoundError,
    IntegrationRouter,
    RouteDispatchResult,
)
from .integration import (
    StreamingPipelineSettings,
    TradePulsePlatform,
    build_tradepulse_platform,
)
from .module_orchestrator import (
    ModuleDefinition,
    ModuleExecutionDynamics,
    ModuleExecutionError,
    ModuleHandler,
    ModuleOrchestrator,
    ModuleRunResult,
    ModuleRunSummary,
    ModuleTimelineEntry,
)

__all__ = [
    "GatewayRequest",
    "IntegrationRoute",
    "IntegrationRouteConflictError",
    "IntegrationRouteError",
    "IntegrationRouteNotFoundError",
    "IntegrationRouter",
    "RouteDispatchResult",
    "ModuleDefinition",
    "ModuleExecutionDynamics",
    "ModuleExecutionError",
    "ModuleHandler",
    "ModuleOrchestrator",
    "ModuleRunResult",
    "ModuleRunSummary",
    "ModuleTimelineEntry",
    "StreamingPipelineSettings",
    "TradePulsePlatform",
    "build_tradepulse_platform",
]
