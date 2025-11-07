"""Neural controller orchestration and TradePulse bridge."""

from __future__ import annotations

from typing import Any, Dict

from ..core.emh_engine import EMHSSM, Params, State
from ..estimation.ekf import EMHEKF, EKFConfig
from ..estimation.belief import VolBelief
from ..policy.controller import BasalGangliaController, PolicyConfig
from ..risk.cvar_gate import CVARGate
from ..risk.homeostatic import HomeostaticModule, HomeoConfig


class NeuralMarketController:
    """Orchestrates EMH → Belief → Homeostasis → EKF → Policy → CVaR."""

    def __init__(
        self,
        params: Params,
        ekf_cfg: EKFConfig,
        policy_cfg: PolicyConfig,
        risk_cfg: dict,
        homeo_cfg: HomeoConfig,
    ) -> None:
        self.model = EMHSSM(params, State())
        self.ekf = EMHEKF(params, ekf_cfg)
        self.belief = VolBelief()
        self.ctrl = BasalGangliaController(policy_cfg)
        self.cvar = CVARGate(risk_cfg["cvar_alpha"], risk_cfg["cvar_limit"], risk_cfg["lookback"])
        self.homeo = HomeostaticModule(homeo_cfg)

    @classmethod
    def from_yaml(cls, path: str) -> "NeuralMarketController":
        import yaml

        with open(path, "r", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh)
        params = Params(**cfg["model"])
        ekf_cfg = EKFConfig(**cfg["ekf"])
        policy_cfg = PolicyConfig(**cfg["policy"])
        homeo_cfg = HomeoConfig(**cfg["homeostasis"])
        return cls(params, ekf_cfg, policy_cfg, cfg["risk"], homeo_cfg)

    def decide(self, obs: Dict[str, float]) -> Dict[str, Any]:
        belief = self.belief.step(obs.get("vol", 0.0))
        snapshot = self.model.step(obs)
        pressure = self.homeo.pressure(snapshot["M"])
        snapshot["S"] = min(1.0, max(0.0, snapshot["S"] + 0.1 * pressure))
        estimate = self.ekf.step(obs)
        action, extras = self.ctrl.decide(estimate, snapshot["mode"], snapshot["RPE"])
        scale = self.cvar.update(obs.get("reward", 0.0))
        extras["alloc_main"] *= scale
        extras["alloc_alt"] *= scale
        return {**estimate, **snapshot, **extras, "alloc_scale": scale, "belief": belief, "action": action}


class NeuralTACLBridge:
    """Dependency-injected bridge to TACL and Kuramoto synchronisation."""

    def __init__(
        self,
        neural: NeuralMarketController,
        tacl_system,
        kuramoto_sync,
        sync_threshold: float = 0.30,
        generations: int = 10,
    ) -> None:
        self.neural = neural
        self.tacl = tacl_system
        self.kuramoto = kuramoto_sync
        self.sync_threshold = float(sync_threshold)
        self.generations = int(generations)

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

    def step(self, obs: Dict[str, float]) -> Dict[str, Any]:
        decision = self.neural.decide(obs)
        temperature = self._action_to_temp(decision["action"])
        coupling = self._mode_to_coupling(decision["mode"])
        allocs = {"main": decision["alloc_main"], "alt": decision["alloc_alt"]}
        tacl_res = self.tacl.optimize(allocs, temperature, generations=self.generations)
        sync = float(self.kuramoto.get_order_parameter())
        desync_throttle = sync < self.sync_threshold
        if desync_throttle:
            tacl_res["allocs"]["main"] *= 0.5
            tacl_res["allocs"]["alt"] *= 0.5
        return {
            **decision,
            **tacl_res,
            "sync_order": sync,
            "temperature": temperature,
            "coupling": coupling,
            "desync_throttle_applied": desync_throttle,
        }
