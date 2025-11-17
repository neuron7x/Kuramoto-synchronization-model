"""
Hierarchical Predictive Coding with Active Inference for Adaptive Trading (HPC-AI v4)

This module integrates Hierarchical Predictive Coding (HPC) with Active Inference (AI)
and Self-Rewarding Deep Reinforcement Learning (SRDRL) for adaptive trading in
non-stationary market environments.

Theoretical foundations:
- Anokhin's Theory of Functional Systems (TFS, 1935-1974)
- Free Energy Principle (FEP, Friston 2009-2025)
- Precision-Weighted Prediction Error (PWPE) minimization
- Metastable phase transitions for market regime detection
"""

import warnings
from typing import Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.optim import Adam


class HPCActiveInferenceModuleV4(nn.Module):
    """
    HPC-AI Module combining hierarchical predictive coding with active inference
    and self-rewarding deep reinforcement learning.
    """

    def __init__(
        self,
        input_dim: int = 10,
        state_dim: int = 128,
        action_dim: int = 3,
        hidden_dim: int = 256,
        hpc_levels: int = 3,
        reward_metrics: int = 3,
        learning_rate: float = 1e-4,
        exploitation_temperature: float = 0.1,
        exploration_temperature: float = 2.0,
    ):
        """
        Initialize HPC-AI Module.

        Args:
            input_dim: Dimension of input features (OHLCV + indicators)
            state_dim: Dimension of latent state representation
            action_dim: Number of actions (Hold=0, Buy=1, Sell=2)
            hidden_dim: Hidden layer dimension
            hpc_levels: Number of hierarchical levels
            reward_metrics: Number of reward metrics (Sharpe, DD, Return)
            learning_rate: Optimizer learning rate
            exploitation_temperature: Temperature for exploitation (sharper, deterministic)
            exploration_temperature: Temperature for exploration (softer, stochastic)
        """
        super().__init__()
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.state_dim = state_dim
        self.input_dim = input_dim
        self.action_dim = action_dim
        self.hpc_levels = hpc_levels

        # Module 1: Afferent Synthesis - Multi-modal feature integration
        self.input_embedding = nn.Linear(input_dim, state_dim)
        self.afferent_encoder = nn.TransformerEncoder(
            nn.TransformerEncoderLayer(
                d_model=state_dim,
                nhead=8,
                dim_feedforward=hidden_dim,
                dropout=0.1,
                batch_first=True,
            ),
            num_layers=3,
        )

        # Module 2: HPC - Hierarchical Predictive Coding with 3 levels
        self.hpc_predictions = nn.ModuleList(
            [
                nn.GRU(state_dim, hidden_dim, bidirectional=True, batch_first=True)
                for _ in range(hpc_levels)
            ]
        )
        self.hpc_errors = nn.ModuleList(
            [nn.Linear(state_dim * 2, state_dim) for _ in range(hpc_levels)]
        )
        self.precision_weights = nn.Parameter(torch.ones(hpc_levels))
        self.residual_skips = nn.ModuleList(
            [nn.Linear(state_dim, hidden_dim * 2) for _ in range(hpc_levels)]
        )

        # Module 3: SRDRL - Actor-Critic with Self-Rewarding
        self.actor = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_dim, action_dim),
        )
        self.critic = nn.Linear(state_dim, 1)
        self.reward_predictor = nn.Sequential(
            nn.Linear(reward_metrics, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
        )
        self.blending_alpha = nn.Parameter(torch.tensor(0.5))

        # Perturbation rectification with learnable scale
        self.perturbation_scale = nn.Parameter(torch.tensor(0.01))

        # Optimizer
        self.optimizer = Adam(self.parameters(), lr=learning_rate)

        # Metastable gate parameters
        self.pwpe_threshold_base = nn.Parameter(torch.tensor(0.2))
        self.k_uncertainty = 0.1
        self.l1_lambda = 0.01
        self.dropout = nn.Dropout(0.1)
        if exploitation_temperature <= 0.0:
            raise ValueError("exploitation_temperature must be positive")

        self.exploitation_temperature = exploitation_temperature
        # Set through the property to keep legacy attribute in sync
        self.exploration_temperature = exploration_temperature

        # Move to device
        self.to(self.device)

    def afferent_synthesis(self, data: pd.DataFrame) -> torch.Tensor:
        """
        Synthesize multi-modal market data into latent state representation.

        Args:
            data: Market data with OHLCV + indicators

        Returns:
            Latent state tensor
        """
        try:
            from core.indicators.kuramoto_ricci_composite import (
                TradePulseCompositeEngine,
            )

            engine = TradePulseCompositeEngine()

            # Ensure DatetimeIndex
            if not isinstance(data.index, pd.DatetimeIndex):
                if "timestamp" in data.columns:
                    data = data.set_index("timestamp")
                elif "date" in data.columns:
                    data = data.set_index("date")
                else:
                    # Create dummy index
                    data.index = pd.date_range(
                        start="2020-01-01", periods=len(data), freq="D"
                    )

            # Analyze market and extract signal
            signal = engine.analyze_market(data)

            # Extract features from signal
            features = pd.DataFrame(
                {
                    "close": data["close"].iloc[-1] if "close" in data.columns else 0.0,
                    "volume": (
                        data["volume"].iloc[-1] if "volume" in data.columns else 0.0
                    ),
                    "kuramoto_R": signal.kuramoto_R,
                    "consensus_R": signal.consensus_R,
                    "coherence": signal.cross_scale_coherence,
                    "static_ricci": signal.static_ricci,
                    "temporal_ricci": signal.temporal_ricci,
                    "topological_transition": signal.topological_transition,
                    "entry_signal": signal.entry_signal,
                    "risk_multiplier": signal.risk_multiplier,
                },
                index=[0],
            )

        except Exception as e:
            warnings.warn(
                f"Failed to use TradePulseCompositeEngine: {e}. Using fallback.",
                RuntimeWarning,
                stacklevel=2,
            )
            # Fallback: use basic features
            required_cols = ["open", "high", "low", "close", "volume"]
            features = data[required_cols].iloc[-1:].copy()

            # Pad to 10 dimensions
            for i in range(len(features.columns), self.input_dim):
                features[f"feature_{i}"] = 0.0

        # Convert to tensor
        features_array = features.values.astype(np.float32)
        if features_array.shape[1] < self.input_dim:
            # Pad to input_dim
            padding = np.zeros(
                (features_array.shape[0], self.input_dim - features_array.shape[1])
            )
            features_array = np.concatenate([features_array, padding], axis=1)
        elif features_array.shape[1] > self.input_dim:
            # Truncate
            features_array = features_array[:, : self.input_dim]

        features_tensor = torch.tensor(features_array, dtype=torch.float32).to(
            self.device
        )

        # Embed and encode
        embedded = self.input_embedding(features_tensor.unsqueeze(0))
        state = self.afferent_encoder(embedded).mean(dim=1)

        return state

    def hpc_forward(self, state: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Forward pass through hierarchical predictive coding layers.

        Args:
            state: Latent state representation

        Returns:
            Tuple of (prediction, total_pwpe)
        """
        # Create sequence for GRU (mock sequence for temporal processing)
        seq_length = 10
        seq_mock = state.unsqueeze(1).repeat(1, seq_length, 1)

        # Top-down predictions (from higher to lower levels)
        predictions = []
        top_down = seq_mock

        for i in reversed(range(self.hpc_levels)):
            pred, _ = self.hpc_predictions[i](top_down)
            # Apply residual skip to last timestep
            pred_last = pred[:, -1, :]
            pred_res = pred_last + self.residual_skips[i](
                state.squeeze(1) if state.dim() > 2 else state
            )
            predictions.append(pred_res)
            # For next level, project back to state_dim and expand to sequence
            pred_state = (
                pred_res[:, : self.state_dim]
                if pred_res.shape[-1] > self.state_dim
                else pred_res
            )
            top_down = pred_state.unsqueeze(1).repeat(1, seq_length, 1)

        # Bottom-up precision-weighted prediction errors
        pwpes = []
        bottom_up = state.squeeze(1) if state.dim() > 2 else state

        for i, (error_layer, precision) in enumerate(
            zip(self.hpc_errors, self.precision_weights)
        ):
            pred = predictions[self.hpc_levels - 1 - i]

            # Prediction error (project pred to state_dim if needed)
            pred_state = (
                pred[:, : self.state_dim] if pred.shape[-1] > self.state_dim else pred
            )
            pe = bottom_up - pred_state

            # Precision-weighted prediction error
            pwpe = precision * pe
            pwpes.append(torch.norm(pwpe))

            # Update bottom-up with error correction
            error_input = torch.cat([pwpe, bottom_up], dim=-1)
            bottom_up = error_layer(error_input) + bottom_up

        # Total PWPE (mean across levels)
        total_pwpe = sum(pwpes) / len(pwpes)

        return predictions[0], total_pwpe

    def compute_self_reward(self, expert_metrics: torch.Tensor, pwpe: float) -> float:
        """
        Compute self-reward with blending and uncertainty modulation.

        Args:
            expert_metrics: Expert metrics (Sharpe, DD, Return)
            pwpe: Precision-weighted prediction error

        Returns:
            Modulated reward value
        """
        predicted_reward = self.reward_predictor(expert_metrics.to(self.device))
        blended_reward = (
            self.blending_alpha * predicted_reward
            + (1 - self.blending_alpha) * expert_metrics.mean()
        )
        modulated_reward = blended_reward * (1 - self.k_uncertainty * pwpe)
        return modulated_reward.item()

    def sr_drl_step(
        self,
        state: torch.Tensor,
        action: torch.Tensor,
        reward: float,
        next_state: torch.Tensor,
        pwpe: float,
    ) -> float:
        """
        Self-rewarding deep RL update step.

        Args:
            state: Current state
            action: Action taken
            reward: Observed reward
            next_state: Next state
            pwpe: Current PWPE

        Returns:
            TD error
        """
        # Compute TD error
        current_v = self.critic(state)
        next_v = self.critic(next_state)
        td_error = reward + 0.99 * next_v - current_v

        # Actor loss with perturbation rectification
        perturbation = torch.randn_like(state) * self.perturbation_scale
        perturbed_state = state + perturbation

        action_logits = self.actor(state)
        perturbed_logits = self.actor(perturbed_state)

        action_probs = F.softmax(action_logits, dim=-1)
        perturbed_probs = F.softmax(perturbed_logits, dim=-1)

        selected_prob = action_probs.gather(1, action.unsqueeze(1).long()).squeeze()
        perturbed_selected = perturbed_probs.gather(
            1, action.unsqueeze(1).long()
        ).squeeze()

        actor_loss = (
            -torch.log(selected_prob + 1e-8) * td_error.detach()
            + 0.5 * (selected_prob - perturbed_selected).pow(2).mean()
        )

        # Critic loss
        critic_loss = td_error.pow(2).mean()

        # Reward prediction loss
        expert_reward = torch.tensor([[reward]], dtype=torch.float32).to(self.device)
        reward_input = torch.tensor([[reward, 0.0, 0.0]], dtype=torch.float32).to(
            self.device
        )
        reward_loss = F.mse_loss(self.reward_predictor(reward_input), expert_reward)

        # L1 regularization on blending alpha
        l1_reg = self.l1_lambda * torch.abs(self.blending_alpha)

        # Total loss
        total_loss = actor_loss + critic_loss + reward_loss + l1_reg

        # Optimize
        self.optimizer.zero_grad()
        total_loss.backward()
        torch.nn.utils.clip_grad_norm_(self.parameters(), max_norm=1.0)
        self.optimizer.step()

        return td_error.item()

    def metastable_transition_gate(self, pwpe: float, d_pwpe_dt: float) -> bool:
        """
        Detect metastable phase transitions.

        Args:
            pwpe: Current PWPE
            d_pwpe_dt: Rate of change of PWPE

        Returns:
            True if metastable transition detected (should hold)
        """
        gate_input = torch.tensor([pwpe, d_pwpe_dt], dtype=torch.float32).to(
            self.device
        )
        gate_input = self.dropout(gate_input)
        gate_value = torch.sigmoid(self.pwpe_threshold_base * gate_input.mean())
        return gate_value.item() > 0.5

    def gumbel_softmax_sample(
        self,
        logits: torch.Tensor,
        temperature: float = 1.0,
        hard: bool = True,
        add_noise: bool = True,
    ) -> torch.Tensor:
        """
        Sample from Gumbel-Softmax distribution for differentiable exploration.

        Args:
            logits: Action logits
            temperature: Temperature parameter (higher = more exploration)
            hard: Whether to use hard sampling with straight-through estimator
            add_noise: If False, skip Gumbel noise for deterministic exploitation

        Returns:
            Sampled action (one-hot or soft)
        """
        if add_noise:
            gumbels = -torch.empty_like(logits).exponential_().log()
            gumbels = (logits + gumbels) / temperature
        else:
            safe_temp = torch.tensor(temperature, device=logits.device)
            safe_temp = torch.clamp(safe_temp, min=1e-6)
            gumbels = logits / safe_temp
        y_soft = F.softmax(gumbels, dim=-1)

        if hard:
            _, y_hard = torch.max(y_soft, dim=-1, keepdim=True)
            y = F.one_hot(y_hard.squeeze(-1), num_classes=logits.size(-1)).float()
            y = (y - y_soft).detach() + y_soft
        else:
            y = y_soft

        return y

    def decide_action(self, data: pd.DataFrame, prev_pwpe: float = 0.0) -> int:
        """
        Decide trading action based on market data.

        Args:
            data: Market data DataFrame
            prev_pwpe: Previous PWPE value

        Returns:
            Action index (0=Hold, 1=Buy, 2=Sell)
        """
        with torch.no_grad():
            state = self.afferent_synthesis(data)
            pred, pwpe = self.hpc_forward(state)

            # Check for metastable transition
            d_pwpe_dt = pwpe.item() - prev_pwpe
            if self.metastable_transition_gate(pwpe.item(), d_pwpe_dt):
                return 0  # Hold

            # Action selection with Gumbel-Softmax
            action_logits = self.actor(state)

            if pwpe.item() > 0.15:
                # High uncertainty: explore with higher temperature and stochasticity
                action_sample = self.gumbel_softmax_sample(
                    action_logits,
                    temperature=self.exploration_temperature,
                    hard=True,
                    add_noise=True,
                )
            else:
                # Low uncertainty: exploit deterministically with sharp temperature
                action_sample = self.gumbel_softmax_sample(
                    action_logits,
                    temperature=self.exploitation_temperature,
                    hard=True,
                    add_noise=False,
                )

            action = torch.argmax(action_sample, dim=-1).item()
            return action

    def get_state_representation(self, data: pd.DataFrame) -> torch.Tensor:
        """Get the latent state representation for market data."""
        with torch.no_grad():
            return self.afferent_synthesis(data)

    def get_pwpe(self, data: pd.DataFrame) -> float:
        """Get the current PWPE value."""
        with torch.no_grad():
            state = self.afferent_synthesis(data)
            _, pwpe = self.hpc_forward(state)
            return pwpe.item()

    @property
    def exploration_temperature(self) -> float:
        """Exploration temperature used for stochastic action selection."""
        return self._exploration_temperature

    @exploration_temperature.setter
    def exploration_temperature(self, value: float) -> None:
        value = float(value)
        if value <= 0.0:
            raise ValueError("exploration_temperature must be positive")
        # Use __dict__ to avoid recursion with the property
        self.__dict__["_exploration_temperature"] = value
        # Keep legacy attribute alias in sync
        self.__dict__["_gumbel_temp"] = value

    @property
    def gumbel_temp(self) -> float:
        """Backward compatible alias for exploration temperature."""
        return self._exploration_temperature

    @gumbel_temp.setter
    def gumbel_temp(self, value: float) -> None:
        # Delegate validation and syncing to the main setter
        self.exploration_temperature = value


__all__ = ["HPCActiveInferenceModuleV4"]
