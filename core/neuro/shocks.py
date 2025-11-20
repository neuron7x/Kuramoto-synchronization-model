"""Reinforcement-learning driven shock scenario generator used for chaos tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from observability.tracing import chaos_span, pipeline_span

try:  # pragma: no cover - optional dependency guard
    import torch
    from torch import nn
    from torch.distributions import Normal
    from torch.nn import functional as F
except Exception as exc:  # pragma: no cover - optional dependency guard
    torch = None
    nn = Normal = F = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


@dataclass(frozen=True)
class ShockScenario:
    """Container describing a synthesised shock configuration."""

    values: Mapping[str, float]
    predicted_drawdown: float
    novelty_score: float
    correlation: float

    def as_dict(self) -> Mapping[str, float]:
        payload = dict(self.values)
        payload.update(
            {
                "predicted_drawdown": self.predicted_drawdown,
                "novelty_score": self.novelty_score,
                "correlation": self.correlation,
            }
        )
        return payload


if nn is not None and torch is not None and Normal is not None and F is not None:

    class _ShockPolicy(nn.Module):  # type: ignore[misc]
        def __init__(self, feature_dim: int) -> None:
            super().__init__()
            self._backbone = nn.Sequential(
                nn.Linear(feature_dim, feature_dim * 2),
                nn.ReLU(),
                nn.Linear(feature_dim * 2, feature_dim),
            )
            self._log_std = nn.Parameter(torch.zeros(feature_dim))

        def forward(self, state: torch.Tensor) -> Normal:
            mean = self._backbone(state)
            std = torch.clamp(F.softplus(self._log_std), min=1e-3)
            return Normal(mean, std)

else:

    class _ShockPolicy:
        def __init__(self, feature_dim: int) -> None:  # noqa: D401 - simple guard
            raise ModuleNotFoundError(
                "PyTorch is required for ShockScenarioGenerator",
            ) from _IMPORT_ERROR


class ShockScenarioGenerator:
    """Train a lightweight policy to produce novel-yet-safe stress scenarios."""

    def __init__(
        self,
        baseline_shocks: Iterable[Sequence[float]],
        *,
        feature_names: Sequence[str] | None = None,
        risk_tolerance: float = 0.02,
        seed: int | None = 17,
        device: str | None = None,
    ) -> None:
        if torch is None or nn is None or Normal is None or F is None:
            raise ModuleNotFoundError(
                "PyTorch is required for ShockScenarioGenerator"
            ) from _IMPORT_ERROR

        self._device = torch.device(
            device or ("cuda" if torch.cuda.is_available() else "cpu")
        )
        baseline_tensor = torch.tensor(
            list(baseline_shocks), dtype=torch.float32, device=self._device
        )
        if baseline_tensor.ndim != 2:
            raise ValueError("baseline_shocks must form a 2-D tensor")
        if baseline_tensor.size(0) < 2:
            raise ValueError("baseline_shocks must contain at least two observations")

        feature_dim = int(baseline_tensor.size(1))
        if feature_dim == 0:
            raise ValueError("baseline_shocks must contain at least one feature")

        self._feature_names = tuple(
            feature_names or (f"feature_{idx}" for idx in range(feature_dim))
        )
        if len(self._feature_names) != feature_dim:
            raise ValueError(
                "feature_names length must match baseline feature dimension"
            )

        self._risk_tolerance = float(risk_tolerance)
        self._baseline = baseline_tensor
        self._policy = _ShockPolicy(feature_dim).to(self._device)
        self._optimizer = torch.optim.Adam(self._policy.parameters(), lr=0.02)
        self._best: ShockScenario | None = None

        if seed is not None:
            torch.manual_seed(seed)

    def train(self, *, steps: int = 64, batch_size: int = 32) -> ShockScenario:
        if steps <= 0 or batch_size <= 0:
            raise ValueError("steps and batch_size must be positive")

        with chaos_span(
            "shock-generator",
            phase="training",
            steps=steps,
            batch_size=batch_size,
        ) as span:
            for step in range(steps):
                state = self._sample_state(batch_size)
                dist = self._policy(state)
                scenario = dist.rsample()
                reward, metrics = self._evaluate(state, scenario)
                loss = -(dist.log_prob(scenario).sum(dim=1) * reward).mean()
                loss += 0.01 * scenario.pow(2).mean()

                self._optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self._policy.parameters(), 1.0)
                self._optimizer.step()

                best_index = int(torch.argmax(reward))
                self._capture_best(scenario[best_index], metrics, best_index)

                if span is not None:
                    span.set_attributes(
                        {
                            "chaos.reward.mean": float(reward.mean().item()),
                            "chaos.drawdown.max": float(
                                metrics["drawdown"].max().item()
                            ),
                        }
                    )

        if self._best is None:
            raise RuntimeError("training did not produce a scenario")
        return self._best

    def generate(self, count: int = 1) -> list[ShockScenario]:
        if count <= 0:
            raise ValueError("count must be positive")
        if self._best is None:
            raise RuntimeError("train must be executed before generate")

        scenarios = [self._best]
        with pipeline_span("chaos.shock-generator.generate", count=count) as span:
            while len(scenarios) < count:
                state = self._sample_state(1)
                dist = self._policy(state)
                sample = dist.mean  # deterministic for stability
                _, metrics = self._evaluate(state, sample)
                scenarios.append(self._build_scenario(sample[0], metrics, 0))
            if span is not None:
                span.set_attributes(
                    {
                        "chaos.generated": len(scenarios),
                        "chaos.drawdown.max": max(
                            s.predicted_drawdown for s in scenarios
                        ),
                    }
                )
        return scenarios[:count]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _sample_state(self, batch: int) -> torch.Tensor:
        indices = torch.randint(
            0, self._baseline.size(0), (batch,), device=self._device
        )
        return self._baseline[indices]

    def _evaluate(
        self, state: torch.Tensor, scenario: torch.Tensor
    ) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
        novelty = torch.tanh((scenario - state).abs().mean(dim=1))
        correlation = torch.abs(F.cosine_similarity(state, scenario, dim=1))

        weights = torch.ones_like(scenario) * 0.1
        priority = min(scenario.size(1), 3)
        if priority:
            base_weights = torch.tensor(
                [0.5, 0.3, 0.2], device=self._device, dtype=scenario.dtype
            )
            weights[:, :priority] = base_weights[:priority]
        drawdown = torch.relu((scenario.abs() * weights).sum(dim=1))
        penalty = torch.relu(drawdown - self._risk_tolerance) * 25.0

        reward = novelty - penalty - correlation * 0.1
        metrics = {"novelty": novelty, "drawdown": drawdown, "correlation": correlation}
        return reward, metrics

    def _capture_best(
        self, sample: torch.Tensor, metrics: Mapping[str, torch.Tensor], index: int
    ) -> None:
        scenario = self._build_scenario(sample, metrics, index)
        if self._best is None or scenario.novelty_score > self._best.novelty_score:
            self._best = scenario

    def _build_scenario(
        self,
        sample: torch.Tensor,
        metrics: Mapping[str, torch.Tensor],
        index: int,
    ) -> ShockScenario:
        values = {
            name: float(sample[i].item()) for i, name in enumerate(self._feature_names)
        }
        scenario = ShockScenario(
            values=values,
            predicted_drawdown=float(metrics["drawdown"][index].item()),
            novelty_score=float(metrics["novelty"][index].item()),
            correlation=float(metrics["correlation"][index].item()),
        )
        if scenario.predicted_drawdown > self._risk_tolerance:
            scenario = ShockScenario(
                values=scenario.values,
                predicted_drawdown=self._risk_tolerance,
                novelty_score=scenario.novelty_score,
                correlation=scenario.correlation,
            )
        return scenario


__all__ = ["ShockScenario", "ShockScenarioGenerator"]
