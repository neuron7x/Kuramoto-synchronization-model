from __future__ import annotations

import logging
from typing import Dict

import numpy as np
import yaml

from ..core.emh_model import EMHSSM
from ..core.params import EKFConfig, HomeoConfig, Params, PolicyConfig, RiskConfig
from ..core.state import EMHState
from ..estimation.belief import VolBelief
from ..estimation.ekf import EMHEKF
from ..homeostasis.homeo import HomeostaticModule
from ..policy.controller import BasalGangliaController
from ..risk.cvar import CVARGate

log = logging.getLogger(__name__)


class TACLSystem:
    """Interface to TACL optimization layer."""

    def optimize(self, allocs: Dict[str, float], temperature: float, generations: int = 10) -> Dict:
        return {"allocs": dict(allocs), "optimized": False}


class KuramotoSync:
    """Interface to Kuramoto order-parameter monitor."""

    def get_order_parameter(self) -> float:
        return 0.5


class NeuralMarketController:
    """Full neuro stack: EMH model + belief + EKF + policy + CVaR + homeostasis."""

    def __init__(
        self,
        params: Params,
        ekf: EKFConfig,
        policy: PolicyConfig,
        risk: RiskConfig,
        homeo: HomeoConfig,
    ):
        self.model = EMHSSM(params, EMHState())
        self.ekf = EMHEKF(params, ekf)
        self.belief = VolBelief()
        self.homeo = HomeostaticModule(homeo.M_target, homeo.k_sigmoid)
        self.ctrl = BasalGangliaController(policy.temp, policy.tau_E_amber)
        self.cvar = CVARGate(risk.cvar_alpha, risk.cvar_limit, risk.lookback)
        self.sync_threshold = 0.3

    @classmethod
    def from_yaml(cls, path: str) -> "NeuralMarketController":
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        params = Params(**cfg["model"])
        ekf = EKFConfig(**cfg["ekf"])
        policy = PolicyConfig(**cfg["policy"])
        risk = RiskConfig(**cfg["risk"])
        homeo = HomeoConfig(**cfg["homeostasis"])
        inst = cls(params, ekf, policy, risk, homeo)
        inst.sync_threshold = float(cfg.get("tacl_bridge", {}).get("sync_threshold", inst.sync_threshold))
        return inst

    def decide(self, obs: Dict[str, float]) -> Dict[str, float]:
        belief = self.belief.step(obs.get("vol", 0.0))
        obs = dict(obs)
        obs["belief_term"] = belief - 0.5

        snapshot = self.model.step(obs)
        pressure = self.homeo.pressure(snapshot["M"])
        snapshot["S"] = float(np.clip(snapshot["S"] + 0.1 * pressure, 0.0, 1.0))

        xhat = self.ekf.step(obs)
        action, extra = self.ctrl.decide(xhat, snapshot["mode"], snapshot["RPE"])

        scale = self.cvar.update(obs.get("reward", 0.0))
        extra["alloc_main"] *= scale
        extra["alloc_alt"] *= scale

        return {
            **snapshot,
            **xhat,
            **extra,
            "alloc_scale": scale,
            "belief": belief,
            "action": action,
        }


class NeuralTACLBridge:
    """Bridge neural controller outputs to TACL system with Kuramoto gating."""

    def __init__(
        self,
        neural: NeuralMarketController,
        tacl: TACLSystem,
        kuramoto: KuramotoSync,
        sync_threshold: float | None = None,
    ):
        self.neural = neural
        self.tacl = tacl
        self.kuramoto = kuramoto
        if sync_threshold is not None:
            self.neural.sync_threshold = float(sync_threshold)

    @staticmethod
    def _action_to_temp(action: str) -> float:
        return {
            "increase_risk": 1.8,
            "decrease_risk": 0.3,
            "switch_to_alt": 1.2,
            "hedge": 0.5,
            "hold": 1.0,
        }.get(action, 1.0)

    @staticmethod
    def _mode_to_coupling(mode: str) -> float:
        return {"GREEN": 0.5, "AMBER": 0.8, "RED": 1.5}.get(mode, 0.5)

    def step(self, obs: Dict[str, float]) -> Dict:
        out = self.neural.decide(obs)
        temperature = self._action_to_temp(out["action"])
        coupling = self._mode_to_coupling(out["mode"])

        initial = {"main": out["alloc_main"], "alt": out["alloc_alt"]}
        tacl_out = self.tacl.optimize(initial, temperature, generations=10)

        sync = float(self.kuramoto.get_order_parameter())
        if sync < self.neural.sync_threshold:
            tacl_out["allocs"]["main"] *= 0.5
            tacl_out["allocs"]["alt"] *= 0.5
            out["desync_throttle_applied"] = True
        else:
            out["desync_throttle_applied"] = False

        return {
            **out,
            **tacl_out,
            "temperature": temperature,
            "coupling": coupling,
            "sync_order": sync,
        }
