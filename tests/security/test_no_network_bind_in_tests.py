from __future__ import annotations

from types import SimpleNamespace

import pytest

from application.runtime import server
from application.runtime.control_gates import Decision, GateDecision, GatePipelineResult
from application.settings import ApiServerSettings, BackendRuntimeSettings
from tests.helpers.control_platform import build_init_result_stub


def test_dry_run_does_not_bind_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail_bind(*_args, **_kwargs):
        raise AssertionError("socket.bind should not be invoked")

    class _DummySocket:
        def bind(self, *args, **kwargs):
            return _fail_bind(*args, **kwargs)

    monkeypatch.setattr("socket.socket", lambda *args, **kwargs: _DummySocket())
    monkeypatch.setattr("uvicorn.Server.run", _fail_bind, raising=False)

    gate_decision = GateDecision(decision=Decision.ALLOW, position_multiplier=1.0, reasons=[])
    gate_result = GatePipelineResult(
        gate=gate_decision, controllers={}, telemetry={"gate_summary": {"decision": gate_decision.decision.value}}
    )
    init_result = build_init_result_stub(
        runtime_settings=BackendRuntimeSettings(),
        server_settings=ApiServerSettings(allow_plaintext=True),
        controllers={},
        telemetry_meta={"effective_config_source": "defaults", "controllers_loaded": []},
        gate_result=gate_result,
    )

    monkeypatch.setattr(server, "initialize_control_platform", lambda **_kwargs: init_result)

    server.run(cli_overrides={"dry_run": True})
