# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Actor-critic agent specialised for coupling with the FHMC controller."""

from __future__ import annotations

import logging
import math
from typing import Mapping

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from core.utils.metrics import get_metrics_collector
from geosync_hpc.multifractal_opt import fractional_update
from rl.core.habit_head import HabitHead, ape_update
from rl.core.interfaces import PolicyContract, ValueContract
from rl.core.modulation_signal import ModulationSignalController
from rl.core.reward_prediction_error import RewardPredictionError
from rl.core.safe_update import SafeUpdateGate
from rl.explore.noise import ColoredNoiseAR1, OUProcess
from runtime.model_registry import ModelMetadata, register_model

logger = logging.getLogger(__name__)


class PolicyNet(nn.Module):
    """Gaussian policy network with a lightweight MLP backbone."""

    def __init__(self, state_dim: int, action_dim: int) -> None:
        super().__init__()
        self.backbone = nn.Sequential(
            nn.Linear(state_dim, 256),
            nn.ReLU(),
            nn.Linear(256, 256),
            nn.ReLU(),
        )
        self.mu = nn.Linear(256, action_dim)
        self.log_std = nn.Parameter(torch.zeros(action_dim))

    def forward(self, state: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:  # type: ignore[override]
        features = self.backbone(state)
        mu = self.mu(features)
        log_std = torch.clamp(self.log_std, -5.0, 2.0)
        return mu, log_std


class ValueNet(nn.Module):
    """State-value estimator used by the critic."""

    def __init__(self, state_dim: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(state_dim, 256),
            nn.ReLU(),
            nn.Linear(256, 256),
            nn.ReLU(),
            nn.Linear(256, 1),
        )

    def forward(self, state: torch.Tensor) -> torch.Tensor:  # type: ignore[override]
        return self.net(state).squeeze(-1)


class ActorCriticFHMC:
    """Actor-critic agent informed by FHMC biomarker feedback."""

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        fhmc,
        *,
        lr: float = 3e-4,
        device: str = "cpu",
    ) -> None:
        self.fhmc = fhmc
        self.device = torch.device(device)
        self.policy: PolicyContract = PolicyNet(state_dim, action_dim).to(self.device)
        self.value: ValueContract = ValueNet(state_dim).to(self.device)
        self.habit = HabitHead(state_dim, action_dim).to(self.device)

        self.opt_policy = torch.optim.Adam(self.policy.parameters(), lr=lr)
        self.opt_value = torch.optim.Adam(self.value.parameters(), lr=lr)
        self.opt_habit = torch.optim.Adam(self.habit.parameters(), lr=lr)

        safe_update_cfg = self.fhmc.cfg.get("safe_update", {})
        self.rpe = RewardPredictionError(
            gamma=float(safe_update_cfg.get("gamma", 0.99)),
            clip_value=safe_update_cfg.get("rpe_clip"),
        )
        self.safe_update = SafeUpdateGate.from_mapping(safe_update_cfg)
        modulation_cfg = self.fhmc.cfg.get("modulation_signal", {})
        self.modulation = ModulationSignalController.from_mapping(modulation_cfg)
        self.grad_clip_norm = float(safe_update_cfg.get("grad_clip_norm", 1.0))
        self.trust_region_kl = float(safe_update_cfg.get("trust_region_kl", 0.1))
        self.drift_threshold = float(safe_update_cfg.get("drift_threshold", 0.2))
        self.rollback_on_drift = bool(safe_update_cfg.get("rollback_on_drift", True))
        self._metrics = get_metrics_collector()
        self._policy_checkpoint = self._snapshot_params(self.policy)
        self._value_checkpoint = self._snapshot_params(self.value)

        explore_cfg = self.fhmc.cfg["explore"]
        self.ou = OUProcess(
            size=action_dim,
            theta=explore_cfg["ou_theta"],
            sigma=explore_cfg["ou_sigma"],
        )
        self.colored = ColoredNoiseAR1(size=action_dim, rho=0.95, sigma=0.05)
        self.beta0 = 1.0
        self.state_dim = state_dim

    @staticmethod
    def _snapshot_params(module: nn.Module) -> dict[str, torch.Tensor]:
        return {name: param.detach().clone() for name, param in module.state_dict().items()}

    @staticmethod
    def _restore_params(module: nn.Module, snapshot: dict[str, torch.Tensor]) -> None:
        module.load_state_dict(snapshot)

    @staticmethod
    def _grad_norm(grads: list[torch.Tensor | None]) -> float:
        norms = [grad.norm(2) for grad in grads if grad is not None]
        if not norms:
            return 0.0
        total = torch.norm(torch.stack(norms))
        return float(total.item())

    def _clip_grads(
        self, grads: list[torch.Tensor | None]
    ) -> tuple[list[torch.Tensor | None], float, float]:
        grad_norm = self._grad_norm(grads)
        if self.grad_clip_norm <= 0 or grad_norm == 0.0:
            return grads, grad_norm, 1.0
        if grad_norm <= self.grad_clip_norm:
            return grads, grad_norm, 1.0
        scale = self.grad_clip_norm / (grad_norm + 1e-8)
        clipped = [grad * scale if grad is not None else None for grad in grads]
        return clipped, grad_norm, scale

    @staticmethod
    def _policy_kl(
        mu_old: torch.Tensor,
        log_std_old: torch.Tensor,
        mu_new: torch.Tensor,
        log_std_new: torch.Tensor,
    ) -> torch.Tensor:
        var_old = torch.exp(2.0 * log_std_old)
        var_new = torch.exp(2.0 * log_std_new)
        numerator = var_old + (mu_old - mu_new).pow(2)
        kl = (log_std_new - log_std_old) + numerator / (2.0 * var_new) - 0.5
        return kl.sum(dim=-1).mean()

    @staticmethod
    def _parameter_drift(module: nn.Module, checkpoint: Mapping[str, torch.Tensor]) -> float:
        deltas = []
        norms = []
        for name, param in module.state_dict().items():
            ref = checkpoint.get(name)
            if ref is None:
                continue
            delta = (param.detach() - ref).float().flatten()
            deltas.append(delta)
            norms.append(ref.detach().float().flatten())
        if not deltas:
            return 0.0
        delta_norm = torch.norm(torch.cat(deltas))
        base_norm = torch.norm(torch.cat(norms))
        return float((delta_norm / (base_norm + 1e-8)).item())

    def reset(self) -> np.ndarray:
        self.ou.reset()
        return np.zeros(self.state_dim, dtype=np.float32)

    def act(self, state_np: np.ndarray) -> np.ndarray:
        state = torch.as_tensor(state_np, dtype=torch.float32, device=self.device).unsqueeze(0)
        orexin = self.fhmc.orexin_value()
        threat = self.fhmc.threat_value()
        beta = self.beta0 + 0.8 * orexin - 0.6 * threat
        mu, log_std = self.policy(state)
        std = torch.exp(log_std)
        dist = torch.distributions.Normal(mu * beta, std)
        action = dist.sample()
        if self.fhmc.state == "WAKE":
            action = action + torch.from_numpy(self.ou.sample()).to(
                self.device, dtype=torch.float32
            )
            if self.fhmc.cfg["explore"].get("use_colored_noise_ppo", False):
                action = action + torch.from_numpy(self.colored.sample()).to(
                    self.device, dtype=torch.float32
                )
        return action.squeeze(0).detach().cpu().numpy()

    def learn(
        self,
        state: np.ndarray,
        action: np.ndarray,
        reward: float,
        next_state: np.ndarray,
        done: bool,
    ) -> None:
        s = torch.as_tensor(state, dtype=torch.float32, device=self.device).unsqueeze(0)
        a = torch.as_tensor(action, dtype=torch.float32, device=self.device).unsqueeze(0)
        r = torch.as_tensor(reward, dtype=torch.float32, device=self.device).unsqueeze(0)
        s_next = torch.as_tensor(next_state, dtype=torch.float32, device=self.device).unsqueeze(0)

        v = self.value(s)
        v_next = self.value(s_next).detach()
        rpe_result = self.rpe.compute(r, v, v_next, done)
        delta_r = rpe_result.delta
        gate_decision = self.safe_update.evaluate(
            rpe_result.metrics,
            metadata={
                "fhmc_state": self.fhmc.state,
                "orexin": float(self.fhmc.orexin_value()),
                "threat": float(self.fhmc.threat_value()),
            },
        )
        modulation_decision = self.modulation.compute(
            rpe_result.metrics,
            orexin=float(self.fhmc.orexin_value()),
            threat=float(self.fhmc.threat_value()),
        )
        policy_snapshot = self._snapshot_params(self.policy)
        modulation_scale = gate_decision.scale * modulation_decision.scale

        self.opt_value.zero_grad()
        (-delta_r.detach() * v).mean().backward()
        grads_value = [
            param.grad.clone() if param.grad is not None else None
            for param in self.value.parameters()
        ]
        grads_value, value_grad_norm, _ = self._clip_grads(grads_value)
        grads_value = [
            grad * modulation_scale if grad is not None else None for grad in grads_value
        ]
        fractional_update(
            list(self.value.parameters()),
            grads_value,
            eta=1.0,
            eta_f=self.fhmc.cfg["fractional_update"]["eta_f"],
            alpha=self.fhmc.cfg["fractional_update"]["levy_alpha"],
            mask_states=self.fhmc.cfg["fractional_update"].get("on_states"),
            current_state=self.fhmc.state,
        )

        with torch.no_grad():
            a_idx = torch.argmax(a, dim=-1)
        a_one_hot = F.one_hot(a_idx, num_classes=self.habit.head.out_features).float()
        self.fhmc.sleep_engine.observe_transition(
            s.squeeze(0).detach().cpu().numpy(),
            a.squeeze(0).detach().cpu().numpy(),
            float(r.item()),
            s_next.squeeze(0).detach().cpu().numpy(),
            float(delta_r.item()),
        )
        ape_update(self.habit, s, a_one_hot, self.opt_habit)

        mu, log_std = self.policy(s)
        std = torch.exp(log_std)
        orexin = self.fhmc.orexin_value()
        threat = self.fhmc.threat_value()
        beta = self.beta0 + 0.8 * orexin - 0.6 * threat
        dist = torch.distributions.Normal(mu * beta, std)
        mu_old = (mu * beta).detach()
        log_std_old = log_std.detach()
        log_prob = dist.log_prob(a).sum(dim=-1)
        loss_policy = -(delta_r.detach() * log_prob).mean()
        self.opt_policy.zero_grad()
        loss_policy.backward()
        grads_policy = [
            param.grad.clone() if param.grad is not None else None
            for param in self.policy.parameters()
        ]
        grads_policy, policy_grad_norm, _ = self._clip_grads(grads_policy)
        grads_policy = [
            grad * modulation_scale if grad is not None else None for grad in grads_policy
        ]
        fractional_update(
            list(self.policy.parameters()),
            grads_policy,
            eta=1.0,
            eta_f=self.fhmc.cfg["fractional_update"]["eta_f"],
            alpha=self.fhmc.cfg["fractional_update"]["levy_alpha"],
            mask_states=self.fhmc.cfg["fractional_update"].get("on_states"),
            current_state=self.fhmc.state,
        )

        mu_new, log_std_new = self.policy(s)
        mu_new = mu_new * beta
        policy_kl = float(
            self._policy_kl(mu_old, log_std_old, mu_new.detach(), log_std_new.detach())
        )
        if self.trust_region_kl > 0 and policy_kl > self.trust_region_kl:
            trust_scale = math.sqrt(self.trust_region_kl / (policy_kl + 1e-8))
            logger.warning(
                "Policy KL %.4f exceeds trust region %.4f, scaling update by %.4f",
                policy_kl,
                self.trust_region_kl,
                trust_scale,
            )
            self._restore_params(self.policy, policy_snapshot)
            trusted_grads = [
                grad * trust_scale if grad is not None else None for grad in grads_policy
            ]
            fractional_update(
                list(self.policy.parameters()),
                trusted_grads,
                eta=1.0,
                eta_f=self.fhmc.cfg["fractional_update"]["eta_f"],
                alpha=self.fhmc.cfg["fractional_update"]["levy_alpha"],
                mask_states=self.fhmc.cfg["fractional_update"].get("on_states"),
                current_state=self.fhmc.state,
            )
            mu_new, log_std_new = self.policy(s)
            mu_new = mu_new * beta
            policy_kl = float(
                self._policy_kl(mu_old, log_std_old, mu_new.detach(), log_std_new.detach())
            )

        policy_drift = self._parameter_drift(self.policy, self._policy_checkpoint)
        rolled_back = False
        rollback_reason = None
        if gate_decision.rollback:
            rollback_reason = "risk_gate"
        elif self.rollback_on_drift and policy_drift > self.drift_threshold:
            rollback_reason = "policy_drift"

        if rollback_reason:
            logger.error(
                "Rolling back policy update due to %s (drift=%.4f, threshold=%.4f)",
                rollback_reason,
                policy_drift,
                self.drift_threshold,
            )
            self._restore_params(self.policy, self._policy_checkpoint)
            self._restore_params(self.value, self._value_checkpoint)
            rolled_back = True

        if not rolled_back:
            self._policy_checkpoint = self._snapshot_params(self.policy)
            self._value_checkpoint = self._snapshot_params(self.value)
        else:
            policy_drift = self._parameter_drift(self.policy, self._policy_checkpoint)

        if self._metrics.enabled:
            agent_label = "fhmc_actor_critic"
            self._metrics.rl_update_scale.labels(agent=agent_label, component="value").set(
                gate_decision.scale
            )
            self._metrics.rl_update_scale.labels(agent=agent_label, component="policy").set(
                gate_decision.scale
            )
            self._metrics.rl_modulation_scale.labels(
                agent=agent_label, component="value", signal="risk_weighted_lr"
            ).set(modulation_scale)
            self._metrics.rl_modulation_scale.labels(
                agent=agent_label, component="policy", signal="risk_weighted_lr"
            ).set(modulation_scale)
            self._metrics.rl_modulation_risk.labels(
                agent=agent_label, signal="risk_weighted_lr"
            ).set(modulation_decision.risk_score)
            self._metrics.rl_modulation_arousal.labels(
                agent=agent_label, signal="risk_weighted_lr"
            ).set(modulation_decision.arousal_boost)
            self._metrics.rl_grad_norm.labels(agent=agent_label, component="value").set(
                value_grad_norm
            )
            self._metrics.rl_grad_norm.labels(agent=agent_label, component="policy").set(
                policy_grad_norm
            )
            self._metrics.rl_policy_kl.labels(agent=agent_label).set(policy_kl)
            self._metrics.rl_policy_drift.labels(agent=agent_label).set(policy_drift)
            if rolled_back and rollback_reason:
                self._metrics.rl_rollback_total.labels(
                    agent=agent_label, reason=rollback_reason
                ).inc()


POLICY_NET_METADATA = register_model(
    ModelMetadata(
        model_id="fhmc_policy_net",
        training_data_window={
            "source": "online_fhmc_transitions",
            "window_shape": "state_dim/action_dim configurable",
            "update_rule": "fractional_update",
        },
        eval_metrics={
            "policy_loss": "tracked",
            "entropy": "tracked",
            "action_stability": "tracked",
        },
        model_type="gaussian_policy_mlp",
        module="rl.core.actor_critic.PolicyNet",
        owners=("rl", "fhmc"),
        notes="Gaussian policy network used by FHMC actor-critic agent.",
    )
)

VALUE_NET_METADATA = register_model(
    ModelMetadata(
        model_id="fhmc_value_net",
        training_data_window={
            "source": "online_fhmc_transitions",
            "window_shape": "state_dim configurable",
            "update_rule": "fractional_update",
        },
        eval_metrics={
            "value_loss": "tracked",
            "td_error": "tracked",
        },
        model_type="value_mlp",
        module="rl.core.actor_critic.ValueNet",
        owners=("rl", "fhmc"),
        notes="State-value estimator for FHMC actor-critic learning loop.",
    )
)

ACTOR_CRITIC_METADATA = register_model(
    ModelMetadata(
        model_id="fhmc_actor_critic_agent",
        training_data_window={
            "source": "online_fhmc_transitions",
            "window_shape": "streaming episodes",
            "update_rule": "actor_critic + habit head",
        },
        eval_metrics={
            "policy_loss": "tracked",
            "value_loss": "tracked",
            "ape_loss": "tracked",
            "reward_prediction_error": "tracked",
            "safe_update_scale": "tracked",
            "policy_kl": "tracked",
            "policy_drift": "tracked",
            "grad_norm": "tracked",
            "rollback_total": "tracked",
        },
        model_type="actor_critic_agent",
        module="rl.core.actor_critic.ActorCriticFHMC",
        owners=("rl", "fhmc"),
        notes="Actor-critic agent integrating FHMC biomarkers and habit head.",
    )
)
