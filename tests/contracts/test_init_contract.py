from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from application.runtime import server
from application.runtime.control_gates import Decision, GateDecision, GatePipelineResult
from application.runtime.init_control_platform import initialize_control_platform
from application.settings import ApiServerSettings, BackendRuntimeSettings
from tests.helpers.control_platform import (
    StubSerotoninController,
    StubThermoController,
    build_gate_result,
    build_init_result_stub,
)


def test_initialize_control_platform_contract() -> None:
    result = initialize_control_platform(
        config_path=None,
        app_factory=lambda **_: SimpleNamespace(name="stub-app"),
        serotonin_factory=lambda *_args, **_kwargs: StubSerotoninController(),
        thermo_factory=lambda *_args, **_kwargs: StubThermoController(),
    )

    assert isinstance(result.runtime_settings, BackendRuntimeSettings)
    assert isinstance(result.server_settings, ApiServerSettings)
    assert result.controllers.keys() >= {"serotonin", "thermo"}
    assert "config_fingerprint" in result.telemetry_meta
    assert callable(result.gate_pipeline)
    assert result.telemetry_meta["controllers_loaded"] == ["serotonin", "thermo"]


def test_dry_run_mode_does_not_bind(monkeypatch: pytest.MonkeyPatch) -> None:
    gate_result = build_gate_result()
    init_result = build_init_result_stub(gate_result=gate_result)

    def _fake_init(**_kwargs):
        return init_result

    monkeypatch.setattr(server, "initialize_control_platform", _fake_init)
    monkeypatch.setattr(
        "uvicorn.Server.run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("uvicorn should not run in dry-run mode")
        ),
        raising=False,
    )

    summary = server.run(cli_overrides={"dry_run": True})
    assert summary is None

    rendered = json.dumps(
        {
            "control_gate_decision": gate_result.gate.decision.value,
            "reasons": gate_result.gate.reasons,
            "position_multiplier": gate_result.gate.position_multiplier,
            "effective_config_source": init_result.telemetry_meta.get(
                "effective_config_source"
            ),
        },
        sort_keys=True,
    )
    assert "control_gate_decision" in rendered
