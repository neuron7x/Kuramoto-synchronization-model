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
    ModuleExecutionError,
    ModuleHandler,
    ModuleOrchestrator,
    ModuleRunResult,
    ModuleRunSummary,
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
    "ModuleExecutionError",
    "ModuleHandler",
    "ModuleOrchestrator",
    "ModuleRunResult",
    "ModuleRunSummary",
    "StreamingPipelineSettings",
    "TradePulsePlatform",
    "build_tradepulse_platform",
]
