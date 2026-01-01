from __future__ import annotations

import copy
import json
import logging
import os
import pkgutil
import sys
import time
import types
from pathlib import Path

import numpy as np
import pytest
import yaml

os.environ.setdefault("TRADEPULSE_LIGHT_IMPORT", "1")
os.environ.setdefault("ADMIN_API_SETTINGS__two_factor_secret", "test-secret")

if "tradepulse" not in sys.modules:
    pkg = types.ModuleType("tradepulse")
    pkg.__path__ = [str(Path(__file__).resolve().parents[2])]
    sys.modules["tradepulse"] = pkg

from ..config import load_default_config
from ..core.emh_model import EMHSSM
from ..core.params import (
    EKFConfig,
    HomeoConfig,
    MarketAdapterConfig,
    Params,
    PolicyConfig,
    RiskConfig,
)
from ..core.state import EMHState
from ..estimation.belief import VolBelief
from ..estimation.ekf import EMHEKF
from ..core.sensory_schema import SCHEMA_VERSION
from ..integration.adapter import MarketDataAdapter
from ..integration.bridge import (
    KuramotoSync,
    NeuralMarketController,
    NeuralTACLBridge,
    TACLSystem,
)
from ..policy.controller import BasalGangliaController
from ..risk.cvar import CVARGate, es_alpha
from ..telemetry.metrics import DecisionMetricsExporter
from ..util.logging import setup_logger
from ..validate.simulate import toy_stream


class DummyTACL(TACLSystem):
    def optimize(self, allocs, temperature, *, generations=None):  # type: ignore[override]
        return {"allocs": dict(allocs), "optimized": True, "temperature": temperature}


class DummyKuramoto(KuramotoSync):
    def get_order_parameter(self) -> float:  # type: ignore[override]
        return 0.25


@pytest.fixture()
def controller() -> NeuralMarketController:
    return NeuralMarketController(
        Params(), EKFConfig(), PolicyConfig(), RiskConfig(), HomeoConfig()
    )


def test_params_backward_imports() -> None:
    from ..core import neuro_params
    from ..core.params import PredictiveConfig, SensoryConfig

    assert SensoryConfig is neuro_params.SensoryConfig
    assert PredictiveConfig is neuro_params.PredictiveConfig


def test_emh_state_bounds() -> None:
    model = EMHSSM(Params(), EMHState())
    for _ in range(256):
        out = model.step(dict(dd=1, liq=1, reg=1, vol=1, reward=0.0, var_breach=True))
        assert 0.0 <= out["H"] <= 1.0
        assert 0.0 <= out["M"] <= 1.0
        assert 0.0 <= out["E"] <= 1.0
        assert 0.0 <= out["S"] <= 1.0


def test_ekf_side_effect_free(controller: NeuralMarketController) -> None:
    ekf = EMHEKF(Params(), EKFConfig())
    state_before = ekf.st.x.copy()
    est = ekf.step(dict(dd=0.2, liq=0.3, reg=0.4, reward=0.0))
    assert set(est) == {"H", "M", "E", "S"}
    assert np.all(ekf.st.x >= 0) and np.all(ekf.st.x <= 1)
    np.testing.assert_array_equal(state_before.shape, ekf.st.x.shape)


def test_vol_belief_updates() -> None:
    belief = VolBelief()
    hi = belief.step(0.9)
    lo = belief.step(0.1)
    assert hi != lo


def test_go_no_go_red_property() -> None:
    ctrl = BasalGangliaController(temp=0.8, tau_E_amber=0.3)
    state = {"H": 0.4, "M": 0.2, "E": 0.1, "S": 0.9}
    for rpe in np.linspace(-1.0, 1.0, num=21):
        action, details = ctrl.decide(state, "RED", float(rpe))
        assert action != "increase_risk"
        assert details["action_probs"]["increase_risk"] == 0.0


def test_go_no_go_amber_requires_energy() -> None:
    ctrl = BasalGangliaController(temp=0.8, tau_E_amber=0.4)
    energetic_state = {"H": 0.6, "M": 0.7, "E": 0.5, "S": 0.5}
    assert (
        ctrl.decide(energetic_state, "AMBER", 0.2)[1]["action_probs"]["increase_risk"]
        > 0.0
    )
    for energy in np.linspace(0.0, 0.39, num=8):
        probs = ctrl.decide({**energetic_state, "E": float(energy)}, "AMBER", 0.2)[1][
            "action_probs"
        ]["increase_risk"]
        assert probs == 0.0
    assert (
        ctrl.decide({**energetic_state, "E": 0.6}, "AMBER", -0.2)[1]["action_probs"][
            "increase_risk"
        ]
        == 0.0
    )


def test_policy_mode_config_changes_behavior(tmp_path: Path) -> None:
    cfg = copy.deepcopy(load_default_config())
    cfg["policy_modes"] = {
        "GREEN": {"temp": 1.1, "gating": 0.0},
        "AMBER": {"temp": 0.8, "gating": 0.6},
        "RED": {"temp": 0.6, "gating": 1.0},
    }
    config_path = tmp_path / "neuro.yaml"
    config_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    controller = NeuralMarketController.from_yaml(str(config_path))
    state = {"H": 0.6, "M": 0.7, "E": 0.5, "S": 0.6}
    green_probs = controller.ctrl.decide(state, "GREEN", 0.2)[1]["action_probs"]
    amber_probs = controller.ctrl.decide(state, "AMBER", 0.2)[1]["action_probs"]

    assert green_probs["increase_risk"] > 0.0
    assert amber_probs["increase_risk"] == 0.0


def test_yaml_with_extra_keys_does_not_break(tmp_path: Path, caplog) -> None:
    cfg = copy.deepcopy(load_default_config())
    cfg["model"]["extra_param"] = 1.23
    cfg["sensory"]["unexpected"] = 0.4
    cfg["unknown_section"] = {"flag": True}
    config_path = tmp_path / "neuro_extra.yaml"
    config_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        controller = NeuralMarketController.from_yaml(str(config_path))

    assert controller is not None
    assert any(
        "Ignoring unknown config key" in record.getMessage()
        for record in caplog.records
    )


def test_cvar_monotonic() -> None:
    gate = CVARGate(alpha=0.95, limit=0.01, lookback=20)
    shocks = np.concatenate([np.linspace(-0.05, -0.02, 10), np.zeros(10)])
    scales = [gate.update(float(x)) for x in shocks]
    assert all(0.0 <= s <= 1.0 for s in scales)
    assert any(s < 1.0 for s in scales)
    last_es = es_alpha(np.array(shocks), 0.95)
    assert last_es >= gate.limit or pytest.approx(last_es, rel=1e-6) == gate.limit
    scaled_returns = np.array(shocks) * scales[-1]
    assert es_alpha(scaled_returns, 0.95) <= gate.limit + 1e-6


def test_bridge_flow(controller: NeuralMarketController) -> None:
    bridge = NeuralTACLBridge(
        controller, DummyTACL(), DummyKuramoto(), sync_threshold=0.3
    )
    obs = dict(
        dd=0.2, liq=0.3, reg=0.4, vol=0.6, reward=0.01, var_breach=False, m_proxy=0.6
    )
    out = bridge.step(obs)
    assert out["desync_throttle_applied"] is True
    assert out["alloc_main"] == pytest.approx(out["allocs"]["main"])
    assert out["alloc_alt"] == pytest.approx(out["allocs"]["alt"])
    assert out["alloc_scale"] <= 1.0
    assert out["temperature"] > 0.0


def test_sensory_confidence_modulates_decision() -> None:
    params = Params(sensory_confidence_gain=1.0)
    controller_full = NeuralMarketController(
        params, EKFConfig(), PolicyConfig(), RiskConfig(), HomeoConfig()
    )
    controller_missing = NeuralMarketController(
        params, EKFConfig(), PolicyConfig(), RiskConfig(), HomeoConfig()
    )
    baseline = dict(
        dd=0.0, liq=0.0, reg=0.0, vol=0.0, reward=0.0, var_breach=False, m_proxy=0.6
    )
    controller_full.decide(dict(baseline))
    controller_missing.decide(dict(baseline))

    updated = dict(
        dd=0.0, liq=0.6, reg=0.4, vol=0.2, reward=0.0, var_breach=False, m_proxy=0.6
    )
    decision_full = controller_full.decide(dict(updated))
    updated.pop("dd")
    decision_missing = controller_missing.decide(dict(updated))

    assert decision_missing["sensory_confidence"] < decision_full["sensory_confidence"]
    assert decision_missing["S"] < decision_full["S"]


def test_bridge_emits_predictive_state_from_config() -> None:
    controller = NeuralMarketController(
        Params(),
        EKFConfig(),
        PolicyConfig(),
        RiskConfig(),
        HomeoConfig(),
        emit_predictive_state=True,
    )
    bridge = NeuralTACLBridge(
        controller, DummyTACL(), DummyKuramoto(), sync_threshold=0.3
    )
    obs = dict(
        dd=0.2, liq=0.3, reg=0.4, vol=0.6, reward=0.01, var_breach=False, m_proxy=0.6
    )
    decision = bridge.step(obs)
    assert "prediction_mu" in decision
    assert "prediction_error_channels" in decision
    assert set(decision["prediction_mu"]) == {"dd", "liq", "reg", "vol"}
    assert set(decision["prediction_error_channels"]) == {"dd", "liq", "reg", "vol"}


def test_toy_stream_invariants(controller: NeuralMarketController) -> None:
    bridge = NeuralTACLBridge(
        controller, DummyTACL(), DummyKuramoto(), sync_threshold=0.3
    )
    for obs in toy_stream(steps=32):
        obs["m_proxy"] = 0.5
        decision = bridge.step(obs)
        for key in ("H", "M", "E", "S"):
            assert 0.0 <= decision[key] <= 1.0
        if decision["mode"] == "RED":
            assert decision["action"] != "increase_risk"


def test_yaml_loader_defaults(tmp_path: Path) -> None:
    config_path = Path("tradepulse/neural_controller/config/neural_params.yaml")
    neural = NeuralMarketController.from_yaml(str(config_path))
    assert pytest.approx(neural.ctrl.tau_E_amber, rel=1e-6) == 0.3
    assert neural.sync_threshold == pytest.approx(0.3, rel=1e-6)
    assert neural.generations == 12
    assert neural.adapter_config == MarketAdapterConfig()


def test_yaml_resource_loader() -> None:
    cfg = load_default_config()
    assert "model" in cfg
    assert cfg["market_adapter"]["max_drawdown_limit"] == pytest.approx(0.2, rel=1e-6)


def test_yaml_resource_loader_missing_optional_include(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_get_data = pkgutil.get_data

    def fake_get_data(package: str, resource: str) -> bytes | None:
        if resource == "neuro_sensory.yaml":
            return None
        return original_get_data(package, resource)

    monkeypatch.setattr(pkgutil, "get_data", fake_get_data)
    cfg = load_default_config()
    assert "model" in cfg


def test_market_adapter_resilience() -> None:
    adapter = MarketDataAdapter()
    obs = adapter.transform({"bid_ask_spread": "nan"}, {"return": "0.1"})
    assert 0.0 <= obs["dd"] <= 1.0
    assert -1.0 <= obs["reward"] <= 1.0


def test_market_adapter_extremes() -> None:
    adapter = MarketDataAdapter(
        max_drawdown_limit=0.2,
        spread_threshold=0.01,
        regime_threshold=0.05,
        hist_max_vol=0.4,
        risk_free=0.01,
        eps=1e-5,
    )
    obs = adapter.transform(
        {"bid_ask_spread": 10.0, "regime_deviation": 5.0, "realized_vol_20": 0.0},
        {"current_drawdown": 0.9, "return": 0.08, "loss": 0.06, "VaR_95": 0.05},
    )
    assert obs["dd"] == pytest.approx(1.0)
    assert obs["liq"] == pytest.approx(1.0)
    assert obs["reg"] == pytest.approx(1.0)
    assert obs["vol"] == pytest.approx(0.0)
    assert obs["var_breach"] is True
    assert -1.0 <= obs["reward"] <= 1.0
    zero_obs = adapter.transform({}, {})
    assert zero_obs["dd"] == 0.0
    assert zero_obs["reward"] == 0.0


def test_schema_version_mismatch_blocks_pipeline(controller: NeuralMarketController) -> None:
    adapter = MarketDataAdapter(schema_version=SCHEMA_VERSION + 1)
    obs = adapter.transform(
        {"bid_ask_spread": 0.02, "regime_deviation": 0.1, "realized_vol_20": 0.2},
        {"current_drawdown": 0.1, "return": 0.01, "loss": 0.02},
    )
    bridge = NeuralTACLBridge(
        controller, DummyTACL(), DummyKuramoto(), sync_threshold=0.3
    )
    with pytest.raises(ValueError, match="schema version"):
        bridge.step(obs)


def test_metrics_exporter_tracks_tail() -> None:
    exporter = DecisionMetricsExporter(tail_window=4)
    for reward in (-0.05, -0.02, 0.01, 0.02):
        metrics = exporter.update(
            {
                "reward": reward,
                "mode": "GREEN",
                "action": "hold",
                "alloc_scale": 1.0,
                "RPE": 0.0,
                "prediction_error": 0.1,
                "timing_sensory_ms": 0.5,
                "timing_predictive_ms": 0.7,
                "timing_model_step_ms": 0.9,
                "timing_ctrl_decide_ms": 1.1,
            }
        )
    assert "tail_ES95" in metrics
    assert metrics["tail_ES95"] >= 0.0
    assert "prediction_error" in metrics
    assert isinstance(metrics["prediction_error"], float)
    for key in (
        "timing_sensory_ms",
        "timing_predictive_ms",
        "timing_model_step_ms",
        "timing_ctrl_decide_ms",
    ):
        assert key in metrics
        assert isinstance(metrics[key], float)


def test_controller_performance(controller: NeuralMarketController) -> None:
    bridge = NeuralTACLBridge(
        controller, DummyTACL(), DummyKuramoto(), sync_threshold=0.3
    )
    obs = dict(
        dd=0.1, liq=0.2, reg=0.3, vol=0.4, reward=0.01, var_breach=False, m_proxy=0.5
    )
    warmup = bridge.step(obs)
    assert warmup["allocs"]
    start = time.perf_counter()
    iterations = 200
    for _ in range(iterations):
        bridge.step(obs)
    elapsed = time.perf_counter() - start
    assert (elapsed / iterations) < 0.003


def test_decision_logging_contains_required_fields(
    controller: NeuralMarketController, caplog: pytest.LogCaptureFixture
) -> None:
    setup_logger()
    bridge = NeuralTACLBridge(
        controller, DummyTACL(), DummyKuramoto(), sync_threshold=0.3
    )
    obs = dict(
        dd=0.2, liq=0.3, reg=0.4, vol=0.6, reward=0.01, var_breach=False, m_proxy=0.6
    )
    with caplog.at_level(logging.INFO, logger="tradepulse.neural_controller.decision"):
        bridge.step(obs)
    records = [
        record
        for record in caplog.records
        if record.name == "tradepulse.neural_controller.decision"
    ]
    assert records, "expected at least one decision log record"
    payload = json.loads(records[-1].message)
    for key in (
        "mode",
        "D",
        "H",
        "M",
        "E",
        "S",
        "RPE",
        "belief",
        "alloc_main",
        "alloc_alt",
        "alloc_scale",
        "temperature",
        "sync_order",
    ):
        assert key in payload
    assert 0.0 <= payload["sync_order"] <= 1.0
