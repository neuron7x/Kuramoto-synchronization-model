from __future__ import annotations

"""Generator that wires DTOs, validators, and API clients into a cohesive SDK."""

from typing import Any

from .template import TemplateGenerator
from .base import GenerationRequest


class SdkGenerator(TemplateGenerator):
    def build_context(self, request: GenerationRequest) -> dict[str, Any]:
        composite = {
            name: value for name, value in sorted(request.sources.items())
        }
        return {
            "sdk_name": request.metadata.get("sdk_name", "TradePulseSDK"),
            "components": composite,
            "metadata": request.metadata,
        }
