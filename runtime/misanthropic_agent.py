"""Risk-sensitive QR-DQN trading agent with CVaR, PER, conformal coverage, and OOD checks."""

from __future__ import annotations

import json
import logging
import os
import random
from collections import deque
from pathlib import Path
from typing import Callable, Deque, Dict, Iterable, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from numpy.random import Generator, default_rng
from scipy.stats import ks_2samp, zscore

from runtime.model_registry import ModelMetadata, register_model

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    file_handler = logging.FileHandler("misanthropic_agent.log")
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


def _seed_all(seed: int) -> None:
    """Seed Python, NumPy, and torch RNGs for reproducibility."""

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():  # pragma: no cover - GPU not used in tests
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(False)


class QRDQN(nn.Module):
    """Quantile Regression DQN head (arXiv:1710.10044)."""

    def __init__(self, state_size: int, action_size: int, quantiles: int = 51) -> None:
        super().__init__()
        self.fc1 = nn.Linear(state_size, 128)
        self.fc2 = nn.Linear(128, 128)
        self.out = nn.Linear(128, action_size * quantiles)
        self.quantiles = quantiles
        self.action_size = action_size

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        x = torch.relu(self.fc1(state))
        x = torch.relu(self.fc2(x))
        return self.out(x).view(-1, self.action_size, self.quantiles)


def quantile_huber_elementwise(
    target: torch.Tensor,
    tau: torch.Tensor,
    prediction: torch.Tensor,
    kappa: float = 1.0,
) -> torch.Tensor:
    """Elementwise Quantile Huber loss without reduction."""

    diff = target - prediction
    huber = torch.where(
        torch.abs(diff) <= kappa,
        0.5 * diff**2,
        kappa * (torch.abs(diff) - 0.5 * kappa),
    )
    return torch.abs(tau - (diff < 0).float()) * huber / kappa


class PERBuffer:
    """Prioritized Experience Replay (proportional) with importance sampling weights."""

    def __init__(
        self,
        capacity: int,
        alpha: float = 0.6,
        beta: float = 0.4,
        eps: float = 1e-3,
        rng: Optional[Generator] = None,
    ) -> None:
        self.capacity = capacity
        self.alpha = alpha
        self.beta = beta
        self.eps = eps
        self.storage: List[Tuple[np.ndarray, int, float, np.ndarray, bool]] = []
        self.priorities: List[float] = []
        self.position = 0
        self._rng: Generator = rng or default_rng()

    def __len__(self) -> int:
        return len(self.storage)

    def add(
        self,
        transition: Tuple[np.ndarray, int, float, np.ndarray, bool],
        priority: Optional[float] = None,
    ) -> None:
        if priority is None:
            priority = max(self.priorities, default=1.0)
        priority = float(abs(priority) + self.eps)

        if len(self.storage) < self.capacity:
            self.storage.append(transition)
            self.priorities.append(priority)
        else:
            self.storage[self.position] = transition
            self.priorities[self.position] = priority
            self.position = (self.position + 1) % self.capacity

    def sample(
        self, batch_size: int
    ) -> Tuple[
        np.ndarray, List[Tuple[np.ndarray, int, float, np.ndarray, bool]], np.ndarray
    ]:
        priorities = np.asarray(self.priorities, dtype=np.float64)
        probs = priorities**self.alpha
        total = probs.sum()
        if not np.isfinite(total) or total <= 0:
            probs = np.full_like(probs, 1.0 / len(self.storage))
        else:
            probs /= total

        indices = self._rng.choice(len(self.storage), batch_size, p=probs)
        samples = [self.storage[i] for i in indices]
        weights = (len(self.storage) * probs[indices]) ** (-self.beta)
        weights = (weights / weights.max()).astype(np.float32)
        return indices, samples, weights

    def update_priorities(
        self, indices: Iterable[int], new_priorities: Iterable[float]
    ) -> None:
        for idx, priority in zip(indices, new_priorities):
            self.priorities[int(idx)] = float(abs(priority) + self.eps)


class MisanthropicAgent:
    """QR-DQN agent with soft CVaR constraint, PER, conformal coverage, and OOD safeguards."""

    def __init__(
        self,
        state_size: int = 6,
        action_size: int = 3,
        quantiles: int = 51,
        capital: float = 10_000.0,
        threat_weights: Optional[List[float]] = None,
        change_point_horizon: int = 10,
        alpha_cvar: float = 0.05,
        cvar_floor: float = -0.05,
        hazard: float = 1 / 2000,
        target_coverage: float = 0.90,
        rng: Optional[Generator] = None,
        *,
        telemetry_hook: Optional[Callable[[Dict[str, float]], None]] = None,
        metrics_path: Optional[Path] = None,
        seed: Optional[int] = None,
        device: Optional[torch.device] = None,
        min_capital_ratio: float = 0.25,
        write_metrics: bool = True,
    ) -> None:
        if threat_weights is None:
            threat_weights = [0.5, 0.2, 0.2, 0.1]

        seed_value = seed if seed is not None else int(os.getenv("TP_SEED", "1337"))
        _seed_all(seed_value)

        self.state_size = state_size
        self.action_size = action_size
        self.quantiles = quantiles

        self.device = device or torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )

        self.model = QRDQN(state_size, action_size, quantiles).to(self.device)
        self.target_model = QRDQN(state_size, action_size, quantiles).to(self.device)
        self.target_model.load_state_dict(self.model.state_dict())
        self.optimizer = optim.AdamW(
            self.model.parameters(), lr=1e-3, weight_decay=1e-4
        )

        self.per_alpha = 0.6
        self.per_beta = 0.4
        self._rng: Generator = rng or default_rng()
        self.replay = PERBuffer(
            100_000, alpha=self.per_alpha, beta=self.per_beta, rng=self._rng
        )
        self.discount = 0.997
        self.batch_size = 64

        self.base_capital = float(capital)
        self.capital = float(capital)
        self.threat_weights = threat_weights
        self.change_point_horizon = change_point_horizon
        self.alpha_cvar = alpha_cvar
        self.cvar_floor = cvar_floor
        self.hazard = hazard
        self.target_coverage = target_coverage
        self.coverage_floor = 0.80
        self.min_capital = float(self.base_capital * min_capital_ratio)

        self.lambda_cvar = 0.0
        self.lambda_step = 1e-3
        self.lambda_max = 10.0

        self.residuals: Deque[float] = deque(maxlen=2000)
        self.breach_streak = 0
        self.breach_patience = 5

        self.run_length = 0
        self.state_window: Deque[np.ndarray] = deque(maxlen=200)
        self.reference_window: Deque[np.ndarray] = deque(maxlen=200)
        self.ood_alpha = 0.05
        self.ood_hold = False

        self.ensemble = [
            nn.Sequential(nn.Linear(state_size, 32), nn.ReLU(), nn.Linear(32, 1)).to(
                self.device
            )
            for _ in range(5)
        ]
        self.ensemble_optimizers = [
            optim.Adam(model.parameters(), lr=1e-3) for model in self.ensemble
        ]

        self.history: Deque[float] = deque(maxlen=5000)
        self.last_state: Optional[np.ndarray] = None
        self.telemetry_hook = telemetry_hook
        if not write_metrics:
            metrics_location: Optional[Path] = None
        elif metrics_path is not None:
            metrics_location = Path(metrics_path)
        else:
            metrics_location = Path(
                os.environ.get(
                    "TP_AGENT_METRICS_PATH", "logs/misanthropic_agent_metrics.jsonl"
                )
            )
        self.metrics_path = metrics_location

    # ------------------------------------------------------------------
    # Feature engineering helpers
    # ------------------------------------------------------------------
    @staticmethod
    def compute_ofi(
        delta_ask: np.ndarray, delta_bid: np.ndarray, levels: int = 10
    ) -> float:
        return float(np.sum(delta_ask - delta_bid) / max(levels, 1))

    def _threat_index(
        self, ofi: float, depth: float, z_vol: float, run_length: int, skew: float
    ) -> float:
        indicator_cp = 1.0 if run_length < self.change_point_horizon else 0.0
        features = [abs(ofi) / max(depth, 1e-6), z_vol, indicator_cp, skew]
        return float(np.dot(self.threat_weights, features))

    def _context_id(self, span: int = 20) -> float:
        if len(self.history) < span + 1:
            return 0.0
        history_list = list(self.history)
        prices = np.asarray(history_list[-(span + 1) :], dtype=float)
        diffs = prices[1:] - prices[:-1]
        if diffs.size < 2:
            return 0.0
        std_prev = float(np.std(diffs[:-1]))
        std_next = float(np.std(diffs[1:]))
        if std_prev < 1e-8 or std_next < 1e-8:
            return 0.0
        covariance = float(np.cov(diffs[:-1], diffs[1:])[0, 1])
        autocorr = covariance / (std_prev * std_next)
        autocorr = float(np.clip(autocorr, -1.0, 1.0))
        if autocorr > 0:
            return 1.0
        if autocorr < 0:
            return -1.0
        return 0.0

    def _update_run_length(self, innovation: float, update: bool) -> int:
        # Lightweight BOCPD-style update that reacts to innovations.
        variance = 1.0
        ll = -0.5 * ((innovation) ** 2) / max(variance, 1e-6)
        growth_score = np.exp(ll) * (1 - self.hazard)
        cp_score = np.exp(ll) * self.hazard
        new_run_length = self.run_length + 1 if growth_score >= cp_score else 0
        if update:
            self.run_length = new_run_length
        return new_run_length

    def _uncertainty(self, state: np.ndarray) -> float:
        with torch.no_grad():
            tensor_state = torch.tensor(
                state, dtype=torch.float32, device=self.device
            ).unsqueeze(0)
            preds: List[float] = []
            for model in self.ensemble:
                was_training = model.training
                model.eval()
                preds.append(model(tensor_state).item())
                if was_training:
                    model.train()
        return float(np.var(preds))

    # ------------------------------------------------------------------
    # Conformal helpers
    # ------------------------------------------------------------------
    def _conformal_quantile(self) -> float:
        if len(self.residuals) < 50:
            return 1.0
        return float(np.quantile(np.abs(self.residuals), self.target_coverage))

    def conformal_coverage(self) -> float:
        if not self.residuals:
            return 1.0
        quantile = self._conformal_quantile()
        return float(np.mean(np.abs(self.residuals) <= quantile))

    # ------------------------------------------------------------------
    # OOD helper
    # ------------------------------------------------------------------
    def _ood_score(self) -> float:
        if (
            len(self.state_window) < self.state_window.maxlen
            or len(self.reference_window) < self.reference_window.maxlen
        ):
            return 0.0
        recent = np.asarray(self.state_window, dtype=float)
        reference = np.asarray(self.reference_window, dtype=float)
        dims = recent.shape[1]
        breaches = 0
        for dim in range(dims):
            p_value = ks_2samp(recent[:, dim], reference[:, dim], method="asymp").pvalue
            if p_value < self.ood_alpha:
                breaches += 1
        return breaches / dims

    # ------------------------------------------------------------------
    # CVaR helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _cvar_numpy(quantiles: np.ndarray, alpha: float) -> float:
        ordered = np.sort(np.asarray(quantiles))
        k = max(1, int(alpha * len(ordered)))
        return float(np.mean(ordered[:k]))

    @staticmethod
    def _cvar_torch(distribution: torch.Tensor, alpha: float) -> torch.Tensor:
        batch, quantiles = distribution.shape
        k = max(1, int(alpha * quantiles))
        sorted_dist, _ = torch.sort(distribution, dim=1)
        return sorted_dist[:, :k].mean(dim=1)

    def _position_size(
        self, threat: float, uncertainty: float, cvar_hat: float, ood_score: float
    ) -> float:
        gate_uncertainty = np.exp(-uncertainty)
        gate_risk = 1.0 if cvar_hat > self.cvar_floor else 0.0
        gate_ood = 1.0 / (1.0 + 3.0 * ood_score)
        sigmoid = 1 / (1 + np.exp(0.5 - threat))
        return float(self.capital * sigmoid * gate_uncertainty * gate_risk * gate_ood)

    # ------------------------------------------------------------------
    # State preparation and action selection
    # ------------------------------------------------------------------
    def _prepare_state(
        self,
        lob_data: Dict[str, np.ndarray],
        price: float,
        *,
        update_trackers: bool,
    ) -> Tuple[np.ndarray, Dict[str, float]]:
        delta_ask = np.asarray(lob_data["delta_ask_vol"], dtype=float)
        delta_bid = np.asarray(lob_data["delta_bid_vol"], dtype=float)
        ofi = self.compute_ofi(delta_ask, delta_bid)
        depth = float(max(lob_data["depth"], 1e-6))
        raw_z = zscore([float(lob_data["rv"])])[0]
        z_vol = float(raw_z) if np.isfinite(raw_z) else 0.0

        history_list = list(self.history)
        mean_history = float(np.mean(history_list[-10:])) if history_list else price
        run_length = self._update_run_length(
            price - mean_history, update=update_trackers
        )
        skew = float(lob_data["skew"])
        threat = self._threat_index(ofi, depth, z_vol, run_length, skew)
        context_id = self._context_id(span=20)

        state = np.array(
            [ofi, depth, z_vol, threat, skew, context_id], dtype=np.float32
        )

        if update_trackers:
            self.state_window.append(state)
            if len(self.reference_window) < self.reference_window.maxlen:
                self.reference_window.append(state)
            self.last_state = state
        else:
            self.last_state = state

        ood_score = self._ood_score()
        self.ood_hold = ood_score > 0.5
        uncertainty = self._uncertainty(state)
        coverage = self.conformal_coverage()

        meta = {
            "ofi": ofi,
            "threat": threat,
            "uncertainty": uncertainty,
            "coverage": coverage,
            "ood_score": ood_score,
        }
        return state, meta

    def _decide_action(
        self, state: np.ndarray, meta: Dict[str, float]
    ) -> Tuple[int, float, float]:
        threat = meta["threat"]
        uncertainty = meta["uncertainty"]
        ood_score = meta["ood_score"]
        coverage = meta["coverage"]

        cvar_hat = 0.0
        size = self._position_size(threat, uncertainty, cvar_hat, ood_score)

        if (
            size <= 0.0
            or threat > 1.0
            or coverage < self.coverage_floor
            or self.ood_hold
        ):
            return 2, 0.0, 0.0

        prev_training = self.model.training
        self.model.eval()
        with torch.no_grad():
            tensor_state = torch.tensor(
                state, dtype=torch.float32, device=self.device
            ).unsqueeze(0)
            q_dist = self.model(tensor_state)
            means = q_dist.mean(dim=2)

            candidates: List[Tuple[int, float, float]] = []
            for action in range(self.action_size):
                distribution = q_dist[0, action].cpu().numpy()
                cvar_action = self._cvar_numpy(distribution, self.alpha_cvar)
                if cvar_action >= self.cvar_floor:
                    candidates.append((action, means[0, action].item(), cvar_action))

            if candidates:
                action, _, cvar_hat = max(candidates, key=lambda entry: entry[1])
            else:
                action, cvar_hat = 2, 0.0
        if prev_training:
            self.model.train()

        # Contra-fade override
        if threat > 0.7 and action != 2:
            action = 1 if meta["ofi"] > 0 else 0

        size = self._position_size(threat, uncertainty, cvar_hat, ood_score)
        return action, size, cvar_hat

    def _post_step(self, price: float) -> None:
        self.history.append(price)

    def _emit_metrics(self, payload: Dict[str, float]) -> None:
        if self.telemetry_hook is not None:
            self.telemetry_hook(payload)

        if self.metrics_path is None:
            return

        try:
            self.metrics_path.parent.mkdir(parents=True, exist_ok=True)
            with self.metrics_path.open("a", encoding="utf-8") as handle:
                json.dump(payload, handle)
                handle.write("\n")
        except OSError:  # pragma: no cover - telemetry path may be unwritable in tests
            logger.debug("Telemetry write skipped", exc_info=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def step(self, lob_data: Dict[str, np.ndarray], price: float) -> Tuple[int, float]:
        state, meta = self._prepare_state(lob_data, price, update_trackers=True)
        action, size, cvar_hat = self._decide_action(state, meta)

        logger.info(
            "step: threat=%.3f unc=%.3f cvar=%.3f action=%d size=%.2f coverage=%.2f ood=%.2f",
            meta["threat"],
            meta["uncertainty"],
            cvar_hat,
            action,
            size,
            meta["coverage"],
            meta["ood_score"],
        )

        self._emit_metrics(
            {
                "threat": float(meta["threat"]),
                "uncertainty": float(meta["uncertainty"]),
                "cvar_hat": float(cvar_hat),
                "action": float(action),
                "size": float(size),
                "coverage": float(meta["coverage"]),
                "ood_score": float(meta["ood_score"]),
                "lambda_cvar": float(self.lambda_cvar),
                "capital": float(self.capital),
            }
        )

        self._post_step(price)
        return int(action), float(size)

    # ------------------------------------------------------------------
    # Learning routines
    # ------------------------------------------------------------------
    def repose(self) -> None:
        if len(self.replay) < self.batch_size:
            return

        indices, batch, importance_weights = self.replay.sample(self.batch_size)
        states, actions, rewards, next_states, dones = zip(*batch)

        states_tensor = torch.tensor(
            np.array(states), dtype=torch.float32, device=self.device
        )
        next_states_tensor = torch.tensor(
            np.array(next_states), dtype=torch.float32, device=self.device
        )
        actions_tensor = torch.tensor(
            actions, dtype=torch.long, device=self.device
        ).unsqueeze(1)
        rewards_tensor = torch.tensor(
            rewards, dtype=torch.float32, device=self.device
        ).unsqueeze(1)
        dones_tensor = torch.tensor(
            dones, dtype=torch.float32, device=self.device
        ).unsqueeze(1)
        weights_tensor = torch.tensor(
            importance_weights, dtype=torch.float32, device=self.device
        ).unsqueeze(1)

        tau = torch.rand(self.batch_size, self.quantiles, device=states_tensor.device)
        tau, _ = tau.sort(dim=1)

        self.model.train()
        all_q = self.model(states_tensor)
        q_dist = all_q.gather(
            1, actions_tensor.unsqueeze(-1).repeat(1, 1, self.quantiles)
        ).squeeze(1)

        with torch.no_grad():
            next_all_q = self.target_model(next_states_tensor)
            next_actions = next_all_q.mean(dim=2).argmax(dim=1).unsqueeze(1)
            next_dist = next_all_q.gather(
                1, next_actions.unsqueeze(-1).repeat(1, 1, self.quantiles)
            ).squeeze(1)
            target_dist = (
                rewards_tensor.repeat(1, self.quantiles)
                + (1 - dones_tensor.repeat(1, self.quantiles))
                * self.discount
                * next_dist
            )

        elementwise = quantile_huber_elementwise(target_dist, tau, q_dist)
        per_sample_loss = elementwise.sum(dim=1, keepdim=True) / self.quantiles

        cvar_hat = self._cvar_torch(q_dist, self.alpha_cvar).unsqueeze(1)
        violation = torch.relu(self.cvar_floor - cvar_hat)
        lagrangian_term = self.lambda_cvar * violation

        loss = (weights_tensor * (per_sample_loss + lagrangian_term)).mean()

        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
        self.optimizer.step()

        with torch.no_grad():
            dual = self.lambda_cvar + self.lambda_step * violation.mean().item()
            self.lambda_cvar = float(np.clip(dual, 0.0, self.lambda_max))

        td_error = (target_dist - q_dist).abs().mean(dim=1)
        td_error = td_error.clamp_min(1e-6).detach().cpu().numpy()
        self.replay.update_priorities(indices, td_error)

        for param, target_param in zip(
            self.model.parameters(), self.target_model.parameters()
        ):
            target_param.data.copy_(
                0.005 * param.data + (1 - 0.005) * target_param.data
            )

        for ensemble_model, optimizer in zip(self.ensemble, self.ensemble_optimizers):
            predictions = ensemble_model(states_tensor.detach())
            ensemble_loss = nn.MSELoss()(predictions, rewards_tensor.detach())
            optimizer.zero_grad()
            ensemble_loss.backward()
            optimizer.step()

        logger.info(
            "repose: loss=%.4f lambda=%.4f", float(loss.item()), self.lambda_cvar
        )

    def train(self, env, episodes: int = 100, *, save_artifacts: bool = True) -> None:
        for episode in range(episodes):
            state_dict = env.reset()
            state, meta = self._prepare_state(
                state_dict["lob_data"], state_dict["price"], update_trackers=True
            )
            done = False
            episode_reward = 0.0

            while not done:
                action, size, cvar_hat = self._decide_action(state, meta)
                logger.info(
                    "train-step: episode=%d threat=%.3f unc=%.3f cvar=%.3f action=%d size=%.2f",
                    episode,
                    meta["threat"],
                    meta["uncertainty"],
                    cvar_hat,
                    action,
                    size,
                )

                self._post_step(state_dict["price"])

                next_state_dict, reward, done = env.step(action)
                episode_reward += float(reward)

                with torch.no_grad():
                    tensor_state = torch.tensor(
                        state, dtype=torch.float32, device=self.device
                    ).unsqueeze(0)
                    prediction = self.model(tensor_state).mean().item()
                self.residuals.append(float(reward - prediction))

                if done:
                    next_state = np.zeros_like(state)
                    next_meta = {
                        "threat": 0.0,
                        "uncertainty": 0.0,
                        "coverage": self.conformal_coverage(),
                        "ood_score": 0.0,
                        "ofi": 0.0,
                    }
                else:
                    next_state, next_meta = self._prepare_state(
                        next_state_dict["lob_data"],
                        next_state_dict["price"],
                        update_trackers=True,
                    )

                self.replay.add((state, action, float(reward), next_state, bool(done)))
                if len(self.replay) >= self.batch_size:
                    self.repose()

                state = next_state
                meta = next_meta
                state_dict = next_state_dict

            coverage = self.conformal_coverage()
            if coverage < self.coverage_floor:
                self.breach_streak += 1
            else:
                self.breach_streak = 0

            if self.breach_streak >= self.breach_patience:
                logger.warning(
                    "coverage breach streak=%d -> extra repose", self.breach_streak
                )
                for _ in range(3):
                    self.repose()
                self.breach_streak = 0

            logger.info(
                "episode=%d reward=%.4f coverage=%.3f lambda=%.4f",
                episode,
                episode_reward,
                coverage,
                self.lambda_cvar,
            )

        if save_artifacts:
            torch.save(self.model.state_dict(), "misanthropic_agent.pth")
            try:
                current_device = self.device
                dummy_input = torch.randn(1, self.state_size, device="cpu")
                model_cpu = self.model.to("cpu")
                torch.onnx.export(
                    model_cpu, dummy_input, "agent.onnx", opset_version=11
                )
                self.model.to(current_device)
                self.target_model.to(current_device)
                for ensemble_model in self.ensemble:
                    ensemble_model.to(current_device)
            except (
                Exception
            ) as exc:  # pragma: no cover - export failures should not break training
                logger.warning("ONNX export skipped: %s", exc)

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------
    def evaluate_stream(
        self,
        stream: Iterable[Tuple[Dict[str, np.ndarray], float]],
        fee: float = 0.0,
    ) -> Dict[str, float]:
        prices: List[float] = []
        pnl: List[float] = [0.0]
        ofi_values: List[float] = []
        price_changes: List[float] = []

        last_price: Optional[float] = None
        current_position = 0.0

        for lob_data, price in stream:
            action, _ = self.step(lob_data, price)
            if action == 0:
                current_position = 1.0
            elif action == 1:
                current_position = -1.0
            else:
                current_position = 0.0

            if last_price is not None:
                pnl.append(
                    pnl[-1]
                    + current_position * (price - last_price)
                    - fee * abs(current_position)
                )
                ofi_values.append(
                    self.compute_ofi(
                        lob_data["delta_ask_vol"], lob_data["delta_bid_vol"]
                    )
                )
                price_changes.append(price - last_price)

            prices.append(price)
            last_price = price

        pnl_array = np.asarray(pnl[1:], dtype=float)
        coverage = self.conformal_coverage()

        if pnl_array.size == 0:
            return {
                "pnl_mean": 0.0,
                "cvar_95": 0.0,
                "coverage": coverage,
                "r2_ofi": 0.0,
            }

        negative = pnl_array[pnl_array < 0]
        if negative.size:
            k = max(1, int(0.05 * negative.size))
            cvar_95 = float(np.mean(np.sort(negative)[:k]))
        else:
            cvar_95 = 0.0

        if len(ofi_values) > 5:
            x = np.asarray(ofi_values, dtype=float)
            y = np.asarray(price_changes, dtype=float)
            X = np.column_stack([np.ones_like(x), x])
            beta, *_ = np.linalg.lstsq(X, y, rcond=None)
            y_hat = X @ beta
            ssr = np.sum((y_hat - y.mean()) ** 2)
            sst = np.sum((y - y.mean()) ** 2)
            r2 = float(ssr / sst) if sst > 0 else 0.0
        else:
            r2 = 0.0

        return {
            "pnl_mean": float(np.mean(pnl_array)),
            "cvar_95": cvar_95,
            "coverage": coverage,
            "r2_ofi": r2,
        }

    # ------------------------------------------------------------------
    # Thermodynamic controller bridge
    # ------------------------------------------------------------------
    def apply_thermo_feedback(
        self,
        *,
        latency_ratio: float,
        coherency: float,
        tail_risk: float,
        coverage_shortfall: float,
    ) -> None:
        """Adjust internal risk budgets from thermodynamic feedback."""

        tail_penalty = max(tail_risk, 0.0)
        latency_penalty = max(latency_ratio - 1.0, 0.0)
        coherence_bonus = max(coherency, 0.0)

        if tail_penalty > 0.0 or latency_penalty > 0.0 or coverage_shortfall > 0.0:
            delta_lambda = (
                0.5 * tail_penalty + 0.2 * latency_penalty + 0.3 * coverage_shortfall
            )
            self.lambda_cvar = float(
                np.clip(self.lambda_cvar + delta_lambda, 0.0, self.lambda_max)
            )

            reduction = (
                0.05 * latency_penalty + 0.1 * tail_penalty + 0.08 * coverage_shortfall
            )
            self.capital = max(self.min_capital, self.capital * (1.0 - reduction))
        else:
            relaxation = 0.05 * coherence_bonus
            self.lambda_cvar = float(max(0.0, self.lambda_cvar - relaxation))
            recovery = 0.02 * coherence_bonus
            self.capital = min(self.base_capital, self.capital * (1.0 + recovery))

    def record_metrics(self, metrics: Dict[str, float]) -> None:
        """Public helper so external controllers can push telemetry."""

        self._emit_metrics(metrics)


QRDQN_METADATA = register_model(
    ModelMetadata(
        model_id="misanthropic_qrdqn",
        training_data_window={
            "source": "streaming_lob_features",
            "window_shape": "state_dim=6",
            "reference_window": "200 states",
            "replay_buffer": "100000 transitions",
        },
        eval_metrics={
            "target_coverage": 0.90,
            "cvar_floor": -0.05,
            "ood_alert_threshold": 0.5,
        },
        model_type="qrdqn",
        module="runtime.misanthropic_agent.QRDQN",
        owners=("runtime", "risk-control"),
        notes="Primary QR-DQN policy backbone for the misanthropic trading agent.",
    )
)

MISANTHROPIC_AGENT_METADATA = register_model(
    ModelMetadata(
        model_id="misanthropic_agent_policy",
        training_data_window={
            "source": "online_policy_learning",
            "window_shape": "per-step updates + PER buffer",
            "reference_window": "200 state tracker",
        },
        eval_metrics={
            "coverage_floor": 0.80,
            "capital_guard": "min_capital_ratio",
            "lambda_cvar_max": 10.0,
        },
        model_type="agent",
        module="runtime.misanthropic_agent.MisanthropicAgent",
        owners=("runtime", "risk-control"),
        notes="Composite agent policy with CVaR, OOD, and conformal coverage gates.",
    )
)
