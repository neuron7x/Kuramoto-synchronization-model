from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cognitive_mirror_methods.system.interfaces.public_api import execute
from cognitive_mirror_methods.system.orchestration import pipeline as pipeline_mod
from cognitive_mirror_methods.system.orchestration.pipeline import run_pipeline


def test_method_schema_has_required_contract_fields() -> None:
    schema = json.loads(Path("cognitive_mirror_methods/schemas/method.schema.json").read_text())
    required = set(schema["required"])
    assert {"id", "definition", "input", "process", "output", "validation", "failure_modes", "example"} <= required


def test_prompt_registry_has_versioned_prompt() -> None:
    text = Path("cognitive_mirror_methods/prompts/registry.yaml").read_text()
    assert "version:" in text
    assert "finalizer_mirror" in text


# ── Runtime contract enforcement (hot path: public_api → router → pipeline) ──
# The schema/prompt tests above check declared contracts; these prove the
# contract is ENFORCED at execution — malformed input or a malformed module
# response fails closed to a canonical BLOCKED, never a leaked exception.


def _valid_request(module: str = "intent", text: str = "привіт світ", **over: Any) -> dict[str, Any]:
    request: dict[str, Any] = {
        "request_id": "r1",
        "module": module,
        "operation": "run",
        "input": {"text": text},
        "context": {},
        "constraints": {},
        "output_format": "json",
        "language": "uk",
    }
    request.update(over)
    return request


def test_valid_request_passes() -> None:
    response = execute(_valid_request())
    assert response["status"] == "PASS"
    assert response["output"]["text"] == "привіт світ"


def test_unknown_module_returns_blocked() -> None:
    response = execute(_valid_request(module="does_not_exist"))
    assert response["status"] == "BLOCKED"
    assert "unknown module" in response["errors"]


def test_non_dict_input_returns_blocked_not_exception() -> None:
    bad = _valid_request()
    bad["input"] = "not-an-object"
    response = execute(bad)
    assert response["status"] == "BLOCKED"
    assert any("invalid input" in e for e in response["errors"])


def test_non_dict_request_returns_blocked_not_exception() -> None:
    response = execute("totally-not-a-request")  # type: ignore[arg-type]
    assert response["status"] == "BLOCKED"
    assert any("invalid request" in e for e in response["errors"])


def test_missing_contract_keys_return_blocked() -> None:
    response = execute({"module": "intent", "input": {"text": "x"}})
    assert response["status"] == "BLOCKED"
    assert any(e.startswith("missing:") for e in response["errors"])


def test_pipeline_blocks_on_malformed_module_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline_mod, "route_request", lambda request: {"status": "PASS"})
    response = run_pipeline(_valid_request())
    assert response["status"] == "BLOCKED"
    assert any("malformed module response" in e for e in response["errors"])


def test_pipeline_happy_path_passes() -> None:
    response = run_pipeline(_valid_request())
    assert response["status"] == "PASS"
    assert len(response["output"]["results"]) >= 1
