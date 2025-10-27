"""Neuroeconomic decision core with lightweight graph-based reinforcement updates."""

from __future__ import annotations

from typing import Dict, Mapping, Sequence, Tuple

try:  # pragma: no cover - optional dependency guard
    import torch
    from torch import Tensor, nn
except Exception as exc:  # pragma: no cover - optional dependency guard
    torch = None  # type: ignore[assignment]
    Tensor = nn = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


if torch is not None and nn is not None:

    class _NeuroGraphEncoder(nn.Module):  # type: ignore[misc]
        """Single message passing step over a fixed cortico-striatal graph."""

        def __init__(self, adjacency: Tensor, hidden_dim: int) -> None:
            super().__init__()
            if adjacency.ndim != 2 or adjacency.size(0) != adjacency.size(1):
                raise ValueError("adjacency must be a square matrix")
            if adjacency.size(0) == 0:
                raise ValueError("adjacency must contain at least one node")

            self.register_buffer("_adjacency", adjacency)
            degree = adjacency.sum(dim=1, keepdim=True).clamp(min=1.0)
            self.register_buffer("_degree", degree)

            self._encoder = nn.Linear(1, hidden_dim)
            self._propagator = nn.Linear(hidden_dim, hidden_dim)
            self._activation = nn.Tanh()

        def forward(self, features: Tensor) -> Tensor:  # type: ignore[override]
            if features.ndim != 2 or features.size(1) != 1:
                raise ValueError("features must be of shape [num_nodes, 1]")
            if features.size(0) != self._adjacency.size(0):
                raise ValueError("feature dimension must match adjacency")

            encoded = self._encoder(features)
            messages = torch.matmul(self._adjacency, encoded) / self._degree
            combined = self._propagator(messages + encoded)
            activated = self._activation(combined)
            return activated.mean(dim=0)


    class AdvancedNeuroEconCore(nn.Module):  # type: ignore[misc]
        """Graph-based actor-critic core inspired by cortico-striatal circuitry."""

        def __init__(
            self,
            *,
            hidden_dim: int = 64,
            gamma: float = 0.95,
            alpha: float = 0.1,
            dopamine_scale: float = 0.54,
            risk_tolerance: float = 0.48,
            uncertainty_reduction: float = 0.30,
            psychiatric_mod: float = 1.0,
            seed: int | None = 42,
            device: str | None = None,
            adjacency: Sequence[Sequence[float]] | None = None,
        ) -> None:
            super().__init__()
            if torch is None or nn is None:
                raise ModuleNotFoundError("PyTorch is required for AdvancedNeuroEconCore") from _IMPORT_ERROR

            self.gamma = float(gamma)
            self.alpha = float(alpha)
            self.dopamine_scale = float(dopamine_scale)
            self.risk_tolerance = float(risk_tolerance)
            self.uncertainty_reduction = float(uncertainty_reduction)
            self.psychiatric_mod = float(psychiatric_mod)

            adjacency_tensor = self._build_adjacency(adjacency)
            self._device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
            adjacency_tensor = adjacency_tensor.to(self._device)
            self._graph = _NeuroGraphEncoder(adjacency_tensor, hidden_dim).to(self._device)
            self._actor = nn.Sequential(  # type: ignore[operator]
                nn.Linear(1, hidden_dim),
                nn.Tanh(),
                nn.Linear(hidden_dim, 1),
            ).to(self._device)
            self._critic = nn.Sequential(  # type: ignore[operator]
                nn.Linear(hidden_dim, hidden_dim),
                nn.Tanh(),
                nn.Linear(hidden_dim, 1),
            ).to(self._device)

            self._q_values: Dict[Tuple[float, int], float] = {}
            self._num_nodes = int(adjacency_tensor.size(0))

            if seed is not None:
                torch.manual_seed(seed)

        @staticmethod
        def _build_adjacency(
            adjacency: Sequence[Sequence[float]] | None,
        ) -> Tensor:
            if adjacency is None:
                adjacency = (
                    (1.0, 0.6, 0.2, 0.1),
                    (0.6, 1.0, 0.5, 0.3),
                    (0.2, 0.5, 1.0, 0.4),
                    (0.1, 0.3, 0.4, 1.0),
                )
            tensor = torch.tensor(adjacency, dtype=torch.float32)
            if tensor.ndim != 2 or tensor.size(0) != tensor.size(1):
                raise ValueError("adjacency must be a square matrix")
            return tensor

        def forward(self, features: Tensor) -> Tensor:  # type: ignore[override]
            return self._graph(features)

        def _coerce_state(self, state: float | int) -> float:
            try:
                return float(state)
            except TypeError as exc:  # pragma: no cover - defensive
                raise TypeError("state must be a numeric scalar") from exc

        def _encode_state(self, state_value: float) -> Tensor:
            features = torch.zeros(self._num_nodes, 1, device=self._device)
            features[0, 0] = state_value
            if self._num_nodes > 1:
                features[1, 0] = self.risk_tolerance
            if self._num_nodes > 2:
                features[2, 0] = self.gamma
            if self._num_nodes > 3:
                features[3, 0] = self.uncertainty_reduction
            return self._graph(features)

        def get_q_value(self, state: float | int, action: int) -> float:
            key = (self._coerce_state(state), int(action))
            return self._q_values.get(key, 0.0)

        def update_Q(
            self,
            state: float | int,
            action: int,
            reward: float,
            next_state: float | int,
            next_action: int,
        ) -> float:
            state_value = self._coerce_state(state)
            next_state_value = self._coerce_state(next_state)

            key = (state_value, int(action))
            next_key = (next_state_value, int(next_action))

            current_encoding = self._encode_state(state_value)
            next_encoding = self._encode_state(next_state_value)

            critic_current = float(self._critic(current_encoding).squeeze())
            critic_next = float(self._critic(next_encoding).squeeze())

            current_estimate = self._q_values.get(key, 0.0)
            next_estimate = self._q_values.get(next_key, 0.0)

            td_error = float(reward) + self.gamma * (next_estimate + critic_next) - (
                current_estimate + critic_current
            )
            modulated = td_error * self.dopamine_scale * self.psychiatric_mod
            self._q_values[key] = current_estimate + self.alpha * modulated
            return modulated

        def simulate_decision(self, options: Sequence[Mapping[str, float]]) -> Tuple[int, float]:
            if not options:
                raise ValueError("options must contain at least one candidate")

            values = []
            for option in options:
                reward = float(option.get("reward", 0.0))
                risk = float(option.get("risk", 0.0))
                cost = float(option.get("cost", 0.0))
                adjusted_reward = reward * (1.0 + self.risk_tolerance * risk) * self.psychiatric_mod
                adjusted_cost = cost * (1.0 - self.uncertainty_reduction)
                values.append(adjusted_reward - adjusted_cost)

            value_tensor = torch.tensor(values, dtype=torch.float32, device=self._device).unsqueeze(-1)
            logits = self._actor(value_tensor).squeeze(-1)
            probabilities = torch.softmax(logits, dim=0)
            choice = int(torch.multinomial(probabilities, num_samples=1).item())
            return choice, float(values[choice])

        def train_on_scenario(
            self,
            states: Sequence[float | int],
            actions: Sequence[int],
            rewards: Sequence[float],
        ) -> Sequence[float]:
            if len(states) < 2 or len(actions) < 2 or len(rewards) < 1:
                raise ValueError("scenario sequences must contain at least two transitions")
            if not (len(states) == len(actions) == len(rewards) + 1):
                raise ValueError("states/actions must be one element longer than rewards")

            history: list[float] = []
            for idx in range(len(rewards)):
                delta = self.update_Q(
                    states[idx],
                    actions[idx],
                    rewards[idx],
                    states[idx + 1],
                    actions[idx + 1],
                )
                history.append(delta)
            return history


else:

    class AdvancedNeuroEconCore:  # type: ignore[too-many-ancestors]
        """Fallback that raises a descriptive error when PyTorch is unavailable."""

        def __init__(self, *args: object, **kwargs: object) -> None:  # noqa: D401 - simple guard
            raise ModuleNotFoundError("PyTorch is required for AdvancedNeuroEconCore") from _IMPORT_ERROR


__all__ = ["AdvancedNeuroEconCore"]
