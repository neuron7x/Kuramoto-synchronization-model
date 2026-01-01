"""Actor-critic agent specialised for coupling with the FHMC controller."""

from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from neuropro.multifractal_opt import fractional_update
from rl.core.habit_head import HabitHead, ape_update
from rl.explore.noise import ColoredNoiseAR1, OUProcess
from runtime.model_registry import ModelMetadata, register_model


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
        self.policy = PolicyNet(state_dim, action_dim).to(self.device)
        self.value = ValueNet(state_dim).to(self.device)
        self.habit = HabitHead(state_dim, action_dim).to(self.device)

        self.opt_policy = torch.optim.Adam(self.policy.parameters(), lr=lr)
        self.opt_value = torch.optim.Adam(self.value.parameters(), lr=lr)
        self.opt_habit = torch.optim.Adam(self.habit.parameters(), lr=lr)

        explore_cfg = self.fhmc.cfg["explore"]
        self.ou = OUProcess(
            size=action_dim,
            theta=explore_cfg["ou_theta"],
            sigma=explore_cfg["ou_sigma"],
        )
        self.colored = ColoredNoiseAR1(size=action_dim, rho=0.95, sigma=0.05)
        self.beta0 = 1.0
        self.state_dim = state_dim

    def reset(self) -> np.ndarray:
        self.ou.reset()
        return np.zeros(self.state_dim, dtype=np.float32)

    def act(self, state_np: np.ndarray) -> np.ndarray:
        state = torch.as_tensor(
            state_np, dtype=torch.float32, device=self.device
        ).unsqueeze(0)
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
        a = torch.as_tensor(action, dtype=torch.float32, device=self.device).unsqueeze(
            0
        )
        r = torch.as_tensor(reward, dtype=torch.float32, device=self.device).unsqueeze(
            0
        )
        s_next = torch.as_tensor(
            next_state, dtype=torch.float32, device=self.device
        ).unsqueeze(0)

        v = self.value(s)
        v_next = self.value(s_next).detach()
        gamma = 0.0 if done else 0.99
        delta_r = r + gamma * v_next - v

        self.opt_value.zero_grad()
        (-delta_r.detach() * v).mean().backward()
        grads_value = [
            param.grad.clone() if param.grad is not None else None
            for param in self.value.parameters()
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
        log_prob = dist.log_prob(a).sum(dim=-1)
        loss_policy = -(delta_r.detach() * log_prob).mean()
        self.opt_policy.zero_grad()
        loss_policy.backward()
        grads_policy = [
            param.grad.clone() if param.grad is not None else None
            for param in self.policy.parameters()
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
        },
        model_type="actor_critic_agent",
        module="rl.core.actor_critic.ActorCriticFHMC",
        owners=("rl", "fhmc"),
        notes="Actor-critic agent integrating FHMC biomarkers and habit head.",
    )
)
