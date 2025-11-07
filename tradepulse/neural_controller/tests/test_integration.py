from __future__ import annotations

import os
import sys
import time
import types
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("TRADEPULSE_LIGHT_IMPORT", "1")
os.environ.setdefault("ADMIN_API_SETTINGS__two_factor_secret", "test-secret")

if "tradepulse" not in sys.modules:
    pkg = types.ModuleType("tradepulse")
    pkg.__path__ = [str(Path(__file__).resolve().parents[2])]
    sys.modules["tradepulse"] = pkg

from ..core.emh_model import EMHSSM
from ..core.params import EKFConfig, HomeoConfig, Params, PolicyConfig, RiskConfig
from ..core.state import EMHState
from ..estimation.belief import VolBelief
from ..estimation.ekf import EMHEKF
from ..integration.adapter import MarketDataAdapter
from ..integration.bridge import KuramotoSync, NeuralMarketController, NeuralTACLBridge, TACLSystem
from ..policy.controller import BasalGangliaController
from ..risk.cvar import CVARGate, es_alpha
from ..telemetry.metrics import DecisionMetricsExporter
from ..validate.simulate import toy_stream


class DummyTACL(TACLSystem):
    def optimize(self, allocs, temperature, *, generations=None):  # type: ignore[override]
        return {"allocs": dict(allocs), "optimized": True, "temperature": temperature}


class DummyKuramoto(KuramotoSync):
    def get_order_parameter(self) -> float:  # type: ignore[override]
        return 0.25


@pytest.fixture()
def controller() -> NeuralMarketController:
    return NeuralMarketController(Params(), EKFConfig(), PolicyConfig(), RiskConfig(), HomeoConfig())


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
    for _ in range(128):
        action, _ = ctrl.decide({"H": 0.4, "M": 0.2, "E": 0.1, "S": 0.9}, "RED", 0.5)
        assert action != "increase_risk"


def test_go_no_go_amber_requires_energy() -> None:
    ctrl = BasalGangliaController(temp=0.8, tau_E_amber=0.4)
    allowed_probs = ctrl.decide({"H": 0.6, "M": 0.7, "E": 0.5, "S": 0.5}, "AMBER", 0.2)[1][
        "action_probs"
    ]["increase_risk"]
    blocked_low_energy = ctrl.decide(
        {"H": 0.6, "M": 0.7, "E": 0.1, "S": 0.5}, "AMBER", 0.2
    )[1]["action_probs"]["increase_risk"]
    blocked_negative_rpe = ctrl.decide(
        {"H": 0.6, "M": 0.7, "E": 0.6, "S": 0.5}, "AMBER", -0.2
    )[1]["action_probs"]["increase_risk"]
    assert allowed_probs > 0.0
    assert blocked_low_energy == 0.0
    assert blocked_negative_rpe == 0.0


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
    bridge = NeuralTACLBridge(controller, DummyTACL(), DummyKuramoto(), sync_threshold=0.3)
    obs = dict(dd=0.2, liq=0.3, reg=0.4, vol=0.6, reward=0.01, var_breach=False, m_proxy=0.6)
    out = bridge.step(obs)
    assert out["desync_throttle_applied"] is True
    assert out["alloc_main"] == pytest.approx(out["allocs"]["main"])
    assert out["alloc_alt"] == pytest.approx(out["allocs"]["alt"])
    assert out["alloc_scale"] <= 1.0
    assert out["temperature"] > 0.0


def test_toy_stream_invariants(controller: NeuralMarketController) -> None:
    bridge = NeuralTACLBridge(controller, DummyTACL(), DummyKuramoto(), sync_threshold=0.3)
    for obs in toy_stream(steps=32):
        obs["m_proxy"] = 0.5
        decision = bridge.step(obs)
        for key in ("H", "M", "E", "S"):
            assert 0.0 <= decision[key] <= 1.0


def test_yaml_loader_defaults(tmp_path: Path) -> None:
    config_path = Path("tradepulse/neural_controller/config/neural_params.yaml")
    neural = NeuralMarketController.from_yaml(str(config_path))
    assert pytest.approx(neural.ctrl.tau_E_amber, rel=1e-6) == 0.3
    assert neural.sync_threshold == pytest.approx(0.3, rel=1e-6)
    assert neural.generations == 12


def test_market_adapter_resilience() -> None:
    adapter = MarketDataAdapter()
    obs = adapter.transform({"bid_ask_spread": "nan"}, {"return": "0.1"})
    assert 0.0 <= obs["dd"] <= 1.0
    assert -1.0 <= obs["reward"] <= 1.0


def test_metrics_exporter_tracks_tail() -> None:
    exporter = DecisionMetricsExporter(tail_window=4)
    for reward in (-0.05, -0.02, 0.01, 0.02):
        metrics = exporter.update({"reward": reward, "mode": "GREEN", "action": "hold", "alloc_scale": 1.0, "RPE": 0.0})
    assert "tail_ES95" in metrics
    assert metrics["tail_ES95"] >= 0.0


def test_controller_performance(controller: NeuralMarketController) -> None:
    bridge = NeuralTACLBridge(controller, DummyTACL(), DummyKuramoto(), sync_threshold=0.3)
    obs = dict(dd=0.1, liq=0.2, reg=0.3, vol=0.4, reward=0.01, var_breach=False, m_proxy=0.5)
    warmup = bridge.step(obs)
    assert warmup["allocs"]
    start = time.perf_counter()
    iterations = 200
    for _ in range(iterations):
        bridge.step(obs)
    elapsed = time.perf_counter() - start
    assert (elapsed / iterations) < 0.003


