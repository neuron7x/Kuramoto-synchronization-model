"""Runtime API for BBB-NVU inference."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, StrictStr

from BBB_NVU_Cognitive_Noise_Gate_2026.src.deterministic_engine import (
    DeterministicInferenceEngine,
    load_yaml,
)

OutputProfile = Literal["full", "risk", "actions"]
RuntimeResult = dict[str, Any] | list[dict[str, Any]]


class RuntimeRequest(BaseModel):
    """Single request accepted by the runtime API."""

    model_config = ConfigDict(extra="forbid")

    input_doc: dict[str, Any]
    source_id: StrictStr = "memory.json"


class RuntimeBoundary:
    """Runtime API with explicit timestamp and output profile."""

    def __init__(self, rules: Mapping[str, Any], engine_hash: str | None = None):
        self.engine = DeterministicInferenceEngine.from_rules(
            dict(rules),
            engine_hash=engine_hash,
        )

    @classmethod
    def from_rule_file(
        cls,
        rules_path: str,
        engine_hash: str | None = None,
    ) -> "RuntimeBoundary":
        """Build a runtime boundary from a rule file."""
        return cls(load_yaml(rules_path), engine_hash=engine_hash)

    def evaluate_run(
        self,
        input_doc: dict[str, Any],
        *,
        source_id: str = "memory.json",
        created_at: str,
        profile: OutputProfile = "full",
    ) -> RuntimeResult:
        """Evaluate one input."""
        output = self.engine.build_output(
            input_doc,
            source_id=source_id,
            created_at=created_at,
        )
        if profile == "full":
            return output
        if profile == "risk":
            return output["risk"]
        return output["actions"]

    def evaluate_batch(
        self,
        requests: Sequence[RuntimeRequest | Mapping[str, Any]],
        *,
        created_at: str,
        profile: OutputProfile = "full",
    ) -> list[RuntimeResult]:
        """Evaluate a deterministic batch."""
        outputs: list[RuntimeResult] = []
        for request in requests:
            if isinstance(request, RuntimeRequest):
                runtime_request = request
            else:
                runtime_request = RuntimeRequest.model_validate(request)
            outputs.append(
                self.evaluate_run(
                    runtime_request.input_doc,
                    source_id=runtime_request.source_id,
                    created_at=created_at,
                    profile=profile,
                )
            )
        return outputs
