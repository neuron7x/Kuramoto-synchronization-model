"""Prompt management subsystem providing templating and experiment utilities."""

from .exceptions import (
    PromptError,
    PromptExperimentError,
    PromptGuardrailViolation,
    PromptInjectionDetected,
    PromptTemplateNotFoundError,
)
from .library import PromptExperiment, PromptTemplateLibrary
from .manager import PromptManager, PromptRunObserver, PromptSanitizer
from .models import (
    ContextFragment,
    ParameterSpec,
    PromptContext,
    PromptContextWindow,
    PromptExecutionRecord,
    PromptOutcome,
    PromptRenderResult,
    PromptTemplate,
)
from .system_architect_prompt import (
    ADRTemplate,
    ATAMTemplate,
    ArchitecturalFramework,
    ConfidenceLevel,
    NFRTemplate,
    STPATemplate,
    SystemArchitectPromptTemplate,
    create_system_architect_prompt,
)

__all__ = [
    "ADRTemplate",
    "ATAMTemplate",
    "ArchitecturalFramework",
    "ConfidenceLevel",
    "ContextFragment",
    "NFRTemplate",
    "ParameterSpec",
    "PromptContext",
    "PromptContextWindow",
    "PromptError",
    "PromptExperiment",
    "PromptExperimentError",
    "PromptExecutionRecord",
    "PromptGuardrailViolation",
    "PromptInjectionDetected",
    "PromptManager",
    "PromptOutcome",
    "PromptRenderResult",
    "PromptRunObserver",
    "PromptSanitizer",
    "PromptTemplate",
    "PromptTemplateLibrary",
    "PromptTemplateNotFoundError",
    "STPATemplate",
    "SystemArchitectPromptTemplate",
    "create_system_architect_prompt",
]
