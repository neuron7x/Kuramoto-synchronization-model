"""Implementation of the MisanthropicAgent V2.1 governance specification."""

from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Deque, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from omegaconf import OmegaConf
from pydantic import BaseModel

from core.drift.bocpd import BOCPD
from core.ood.ks import ood_score_ks
from core.replay.per import PERBuffer
from core.risk.cvar import cvar_from_quantiles
from core.ts.har import fit_har, predict_har, update_har
from core.uq.ensembles import DeepEnsembles
from runtime.metrics import gauge_set
from runtime.tacl_guard import TACLGuard


class AgentArchConfig(BaseModel):
    state_dim: int
    action_dim: int
    quantiles: int
    dueling: bool
    noisy_layers: bool


class RiskConfig(BaseModel):
    alpha_cvar: float
    c_cvar: float
    lambda_cvar_init: float
    lambda_cvar_max: float
    eta_cvar: float


class PERConfig(BaseModel):
    alpha: float
    beta: float
    eps: float
    breach_boost: float


class ENBPIConfig(BaseModel):
    window: int
    target: float
    floor: float
    breach_patience: int


class HARConfig(BaseModel):
    lags: List[int]
    alpha: float


class OODConfig(BaseModel):
    alpha: float
    win: int
    hold_threshold: float


class TACLConfig(BaseModel):
    w_lat: float
    w_coh: float
    w_cost: float


class UQConfig(BaseModel):
    heads: int
    lr: float
    bootstrap: bool


class AgentConfig(BaseModel):
    gamma: float
    batch_size: int
    target_soft_tau: float
    risk: RiskConfig
    per: PERConfig
    enbpi: ENBPIConfig
    har: HARConfig
    ood: OODConfig
    tacl: TACLConfig
    uq: UQConfig
    arch: AgentArchConfig


def _make_log_path(log_dir: Path, seed: int) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    run_id = int(time.time() * 1000)
    return log_dir / f"run_{seed}_{run_id}.jsonl"


class NoisyLinear(nn.Linear):
    def __init__(self, in_features: int, out_features: int) -> None:
        super().__init__(in_features, out_features)
        self.register_buffer("weight_noise", torch.zeros(out_features, in_features))
        self.register_buffer("bias_noise", torch.zeros(out_features))
        self.reset_noise()

    def reset_noise(self) -> None:
        epsilon_in = torch.randn(self.in_features, device=self.weight.device)
        epsilon_out = torch.randn(self.out_features, device=self.weight.device)
        self.weight_noise = torch.ger(epsilon_out, epsilon_in)
        self.bias_noise = torch.randn(self.out_features, device=self.weight.device)

    def forward(self, input: torch.Tensor) -> torch.Tensor:  # type: ignore[override]
        if self.training:
            weight = self.weight + self.weight_noise * 0.017
            bias = self.bias + self.bias_noise * 0.017
        else:
            weight = self.weight
            bias = self.bias
        return F.linear(input, weight, bias)


class DuelingQuantileNet(nn.Module):
    def __init__(self, config: AgentArchConfig) -> None:
        super().__init__()
        linear = NoisyLinear if config.noisy_layers else nn.Linear
        self.fc1 = linear(config.state_dim, 128)
        self.fc2 = linear(128, 128)
        self.quantiles = config.quantiles
        if config.dueling:
            self.value_head = linear(128, config.quantiles)
            self.adv_head = linear(128, config.action_dim * config.quantiles)
        else:
            self.head = linear(128, config.action_dim * config.quantiles)
        self.action_dim = config.action_dim
        self.dueling = config.dueling

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        x = torch.relu(self.fc1(state))
        x = torch.relu(self.fc2(x))
        if self.dueling:
            value = self.value_head(x).view(-1, 1, self.quantiles)
            adv = self.adv_head(x).view(-1, self.action_dim, self.quantiles)
            adv_mean = adv.mean(dim=1, keepdim=True)
            q = value + adv - adv_mean
        else:
            q = self.head(x).view(-1, self.action_dim, self.quantiles)
        return q


def quantile_huber_elementwise(
    target: torch.Tensor, tau: torch.Tensor, prediction: torch.Tensor, kappa: float = 1.0
) -> torch.Tensor:
    diff = target - prediction
    abs_diff = torch.abs(diff)
    huber = torch.where(abs_diff <= kappa, 0.5 * diff**2, kappa * (abs_diff - 0.5 * kappa))
    loss = torch.abs(tau - (diff.detach() < 0).float()) * huber / kappa
    return loss


@dataclass
class AgentState:
    prev_obs: Optional[np.ndarray] = None
    prev_action: Optional[int] = None
    episode: int = 0
    step: int = 0


class MisanthropicAgent:
    def __init__(self, config: AgentConfig, *, seed: int, log_dir: Path) -> None:
        self.config = config
        self.device = torch.device("cpu")
        self.seed = seed
        torch.manual_seed(seed)
        np.random.seed(seed)
        self.gamma = config.gamma
        self.batch_size = config.batch_size
        self.replay = PERBuffer(capacity=4096, alpha=config.per.alpha, beta=config.per.beta, eps=config.per.eps)
        self.replay.configure_breach(config.per.breach_boost)
        self.online = DuelingQuantileNet(config.arch).to(self.device)
        self.target = DuelingQuantileNet(config.arch).to(self.device)
        self.target.load_state_dict(self.online.state_dict())
        self.optimizer = torch.optim.Adam(self.online.parameters(), lr=1e-3)
        self.tau = torch.linspace(0.0, 1.0, config.arch.quantiles + 1)[1:]
        self.lambda_cvar = config.risk.lambda_cvar_init
        self.har_state = fit_har(np.linspace(0.01, 0.02, 30), tuple(config.har.lags))
        self.residuals: Deque[float] = deque(maxlen=2000)
        self.coverage_history: Deque[float] = deque(maxlen=100)
        self.enbpi_breach = 0
        self.breach_hold = 0
        self.state = AgentState()
        self.log_path = _make_log_path(log_dir, seed)
        self.log_fp = self.log_path.open("w", encoding="utf-8")
        self.commit_hash = self._resolve_commit()
        self.ood_ref: Deque[np.ndarray] = deque(maxlen=config.ood.win)
        self.ood_live: Deque[np.ndarray] = deque(maxlen=config.ood.win)
        self.ensembles = DeepEnsembles(
            state_dim=config.arch.state_dim, k=config.uq.heads, lr=config.uq.lr, bootstrap=config.uq.bootstrap
        )
        self.ensemble_buffer: List[Tuple[np.ndarray, float]] = []
        self.bocpd = BOCPD(hazard=0.01, z_limit=2.5)
        self.tacl = TACLGuard(
            w_lat=config.tacl.w_lat, w_coh=config.tacl.w_coh, w_cost=config.tacl.w_cost
        )
        self.latest_F = 0.0
        self.repose_calls = 0
        self.last_repose_denied = False

    def _resolve_commit(self) -> str:
        try:
            import subprocess

            return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], encoding="utf-8").strip()
        except Exception:
            return "unknown"

    def _log_event(
        self,
        action: int,
        size: float,
        threat: float,
        ood: float,
        coverage: float,
        q_enbpi: float,
        lambda_cvar: float,
        violation: float,
        lat_ms: float,
        cpu_util: float,
        change_denied: bool,
    ) -> None:
        payload = {
            "ts": time.time(),
            "ep": self.state.episode,
            "step": self.state.step,
            "action": action,
            "size": size,
            "threat": threat,
            "ood": ood,
            "coverage": coverage,
            "q_enbpi": q_enbpi,
            "lambda_cvar": lambda_cvar,
            "cvar_violation": violation,
            "lat_ms": lat_ms,
            "cpu_util": cpu_util,
            "F": self.latest_F,
            "change_denied": change_denied,
            "seed": self.seed,
            "commit": self.commit_hash,
        }
        self.log_fp.write(json.dumps(payload) + "\n")
        self.log_fp.flush()

    def _compute_coverage(self, residual: float) -> Tuple[float, float]:
        self.residuals.append(residual)
        if len(self.residuals) < 20:
            return 1.0, 0.0
        abs_res = np.abs(np.array(self.residuals))
        q = float(np.quantile(abs_res, self.config.enbpi.target))
        coverage = float(np.mean(abs_res <= q))
        self.coverage_history.append(coverage)
        gauge_set("tradepulse_q_enbpi", q)
        return coverage, q

    def _update_replay(self, obs: np.ndarray, action: int, reward: float, next_obs: np.ndarray, done: bool) -> None:
        self.replay.add((obs, action, reward, next_obs, done))
        self.ensemble_buffer.append((obs, reward))
        if len(self.ensemble_buffer) > 1024:
            self.ensemble_buffer.pop(0)

    def _select_action(self, obs: np.ndarray) -> Tuple[int, torch.Tensor]:
        state_t = torch.as_tensor(obs, dtype=torch.float32, device=self.device).unsqueeze(0)
        with torch.no_grad():
            q = self.online(state_t)
            expected = q.mean(dim=-1)
            action = int(torch.argmax(expected, dim=1).item())
        return action, q.squeeze(0)

    def _apply_gates(
        self,
        action: int,
        obs: np.ndarray,
        q_dist: torch.Tensor,
        coverage: float,
        q_enbpi: float,
        residual: float,
    ) -> Tuple[int, float, float, float, float]:
        state_arr = obs.reshape(-1)
        if len(self.ood_ref) < self.config.ood.win:
            self.ood_ref.append(state_arr)
        else:
            self.ood_live.append(state_arr)
        ood_score = 0.0
        if len(self.ood_ref) == self.config.ood.win and len(self.ood_live) == self.config.ood.win:
            ref = np.stack(list(self.ood_ref))
            live = np.stack(list(self.ood_live))
            ood_score = ood_score_ks(ref, live, self.config.ood.alpha)
        size = 1.0 / (1.0 + 3.0 * ood_score)
        if ood_score > self.config.ood.hold_threshold:
            action = 1
        if coverage < self.config.enbpi.floor:
            action = 1
        threat_run = self.bocpd.update(residual)
        threat = 1.0 if threat_run < 5 else 0.0
        if threat > 0.5:
            size *= 0.5
        q_action = q_dist[action]
        cvar_hat = float(cvar_from_quantiles(q_action.unsqueeze(0), self.config.risk.alpha_cvar).item())
        if cvar_hat < self.config.risk.c_cvar:
            action = 1
        return action, size, ood_score, threat, cvar_hat

    def repose(self) -> None:
        if len(self.replay) < self.batch_size:
            return
        idxs, batch, weights = self.replay.sample(self.batch_size)
        states = torch.as_tensor(np.stack([b[0] for b in batch]), dtype=torch.float32)
        actions = torch.as_tensor([b[1] for b in batch], dtype=torch.int64)
        rewards = torch.as_tensor([b[2] for b in batch], dtype=torch.float32)
        next_states = torch.as_tensor(np.stack([b[3] for b in batch]), dtype=torch.float32)
        dones = torch.as_tensor([b[4] for b in batch], dtype=torch.float32)
        self.online.train()
        self.optimizer.zero_grad(set_to_none=True)
        q_dist = self.online(states)
        chosen = q_dist[torch.arange(self.batch_size), actions]
        with torch.no_grad():
            next_q = self.online(next_states).mean(dim=-1)
            next_actions = torch.argmax(next_q, dim=1)
            target_dist = self.target(next_states)
            target = target_dist[torch.arange(self.batch_size), next_actions]
            target = rewards.unsqueeze(1) + self.gamma * (1 - dones.unsqueeze(1)) * target
        tau = self.tau.view(1, -1)
        loss_elements = quantile_huber_elementwise(target, tau, chosen)
        loss_per_sample = loss_elements.mean(dim=1, keepdim=True)
        cvar_hat = cvar_from_quantiles(chosen, self.config.risk.alpha_cvar).view(-1, 1)
        violation = torch.relu(torch.tensor(self.config.risk.c_cvar) - cvar_hat)
        total = (torch.as_tensor(weights).view(-1, 1) * (loss_per_sample + self.lambda_cvar * violation)).mean()
        if not torch.isfinite(total):
            return
        total.backward()
        torch.nn.utils.clip_grad_norm_(self.online.parameters(), 1.0)
        self.optimizer.step()
        with torch.no_grad():
            for online_param, target_param in zip(self.online.parameters(), self.target.parameters()):
                target_param.data.copy_(
                    self.config.target_soft_tau * online_param.data
                    + (1.0 - self.config.target_soft_tau) * target_param.data
                )
        lambda_old = self.lambda_cvar
        lambda_new = float(
            np.clip(
                self.lambda_cvar + self.config.risk.eta_cvar * float(violation.mean().item()),
                0.0,
                self.config.risk.lambda_cvar_max,
            )
        )
        delta = lambda_new - lambda_old
        change_denied = False
        if self.tacl.approve_change("lambda_cvar", delta, override=False):
            self.lambda_cvar = lambda_new
        else:
            change_denied = True
        self.replay.update_priorities(idxs, loss_per_sample.detach().squeeze(1).numpy())
        if self.ensemble_buffer:
            X = np.stack([x for x, _ in self.ensemble_buffer])
            y = np.array([r for _, r in self.ensemble_buffer])
            self.ensembles.update_batch(X, y)
        self.repose_calls += 1
        self.last_repose_denied = change_denied

    def step(self, obs: np.ndarray, reward: float, done: bool, cpu_util: float = 0.2) -> int:
        tic = time.perf_counter()
        self.tacl.begin_step()
        residual = abs(reward)
        update_har(self.har_state, residual, self.config.har.alpha)
        predicted = predict_har(self.har_state)
        residual_delta = residual - predicted
        coverage, q_enbpi = self._compute_coverage(residual_delta)
        if coverage < self.config.enbpi.floor:
            self.enbpi_breach += 1
            self.replay.mark_recent(self.config.enbpi.window)
            if self.enbpi_breach >= self.config.enbpi.breach_patience:
                self.breach_hold = 3
        else:
            self.enbpi_breach = 0
        action, q_dist = self._select_action(obs)
        if self.breach_hold > 0:
            action = 1
        action, size, ood_score, threat, cvar_hat = self._apply_gates(action, obs, q_dist, coverage, q_enbpi, residual_delta)
        if self.state.prev_obs is not None and self.state.prev_action is not None:
            self._update_replay(self.state.prev_obs, self.state.prev_action, reward, obs, done)
        if self.breach_hold > 0:
            for _ in range(3):
                self.repose()
            self.breach_hold -= 1
        else:
            self.repose()
        toc = time.perf_counter()
        lat_ms = (toc - tic) * 1000
        F_value = (
            self.config.tacl.w_lat * lat_ms
            + self.config.tacl.w_coh * (1.0 - coverage)
            + self.config.tacl.w_cost * cpu_util
        )
        self.latest_F = F_value
        self.tacl.end_step(lat_ms, coverage, cpu_util)
        gauge_set("tradepulse_lambda_cvar", self.lambda_cvar)
        gauge_set("tradepulse_ood_score", ood_score)
        self._log_event(action, size, threat, ood_score, coverage, q_enbpi, self.lambda_cvar, max(0.0, self.config.risk.c_cvar - cvar_hat), lat_ms, cpu_util, getattr(self, "last_repose_denied", False))
        self.state.prev_obs = obs
        self.state.prev_action = action
        self.state.step += 1
        if done:
            self.state.episode += 1
            self.state.step = 0
            self.state.prev_obs = None
            self.state.prev_action = None
        return action

    def close(self) -> None:
        self.log_fp.close()


def load_agent_config(path: Path) -> AgentConfig:
    cfg = OmegaConf.load(path)
    return AgentConfig.model_validate(OmegaConf.to_container(cfg, resolve=True))


__all__ = ["MisanthropicAgent", "load_agent_config", "AgentConfig"]
