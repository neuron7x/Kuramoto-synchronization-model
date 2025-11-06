"""Continual learning metrics for FHMC agent validation.

Implements FID, retention, and backward transfer metrics as recommended
in the 2025 audit for robust continual learning validation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np


@dataclass
class ContinualLearningMetrics:
    """Metrics for evaluating continual learning performance."""

    fid_score: float  # Fréchet Inception Distance analogue
    retention_rate: float  # Knowledge retention after new tasks
    backward_transfer: float  # Improvement on old tasks after learning new
    forward_transfer: float  # Performance on new tasks from old knowledge
    catastrophic_forgetting_index: float  # Measure of forgetting


class ContinualLearningEvaluator:
    """Evaluate continual learning with FID, retention, and backward transfer.
    
    Addresses audit recommendation:
    "брак детальних протоколів для retention/backward transfer в continual learning"
    """

    def __init__(self, task_dimension: int = 10) -> None:
        self.task_dimension = task_dimension
        self._task_performances: dict[str, list[float]] = {}
        self._task_embeddings: dict[str, np.ndarray] = {}

    def compute_fid_score(
        self,
        real_embeddings: Iterable[float],
        generated_embeddings: Iterable[float],
    ) -> float:
        """Compute Fréchet Inception Distance analogue for generative replay.
        
        Measures quality of experience replay in continual learning.
        Lower is better (0 = identical distributions).
        
        Note: Uses simplified FID without matrix square root for numerical stability.
        For production use, consider scipy.linalg.sqrtm for exact FID.
        """
        real = np.asarray(real_embeddings, dtype=float).reshape(-1, self.task_dimension)
        generated = np.asarray(generated_embeddings, dtype=float).reshape(-1, self.task_dimension)
        
        if len(real) < 2 or len(generated) < 2:
            return 1.0
        
        # Compute statistics
        mu_real = np.mean(real, axis=0)
        mu_gen = np.mean(generated, axis=0)
        
        cov_real = np.cov(real, rowvar=False)
        cov_gen = np.cov(generated, rowvar=False)
        
        # Add regularization for numerical stability
        cov_real += np.eye(cov_real.shape[0]) * 1e-6
        cov_gen += np.eye(cov_gen.shape[0]) * 1e-6
        
        # Compute simplified FID (mean difference + trace terms)
        mu_diff = mu_real - mu_gen
        
        # Simplified version without matrix sqrt for stability
        # Full FID would use: trace(cov_real + cov_gen - 2*sqrt(cov_real @ cov_gen))
        # This approximation uses: trace(cov_real + cov_gen) - 2*trace(sqrt(diag(cov_real)*diag(cov_gen)))
        trace_term = np.trace(cov_real) + np.trace(cov_gen)
        cross_term = 2 * np.sum(np.sqrt(np.maximum(np.diag(cov_real) * np.diag(cov_gen), 0)))
        
        fid = float(np.sum(mu_diff ** 2) + trace_term - cross_term)
        
        return max(0.0, fid)

    def record_task_performance(self, task_id: str, performance: float) -> None:
        """Record performance on a specific task."""
        if task_id not in self._task_performances:
            self._task_performances[task_id] = []
        self._task_performances[task_id].append(performance)

    def compute_retention_rate(self, task_id: str) -> float:
        """Compute retention rate for a task.
        
        Measures how well the agent retains knowledge of a task over time.
        Returns value in [0, 1] where 1 = perfect retention.
        """
        if task_id not in self._task_performances or len(self._task_performances[task_id]) < 2:
            return 1.0
        
        performances = self._task_performances[task_id]
        initial_perf = performances[0]
        final_perf = performances[-1]
        
        if initial_perf == 0:
            return 1.0 if final_perf >= initial_perf else 0.0
        
        retention = final_perf / initial_perf
        return float(np.clip(retention, 0.0, 2.0))

    def compute_backward_transfer(
        self,
        old_task_id: str,
        performance_before: float,
        performance_after: float,
    ) -> float:
        """Compute backward transfer.
        
        Measures improvement on old task after learning new tasks.
        Positive value indicates positive transfer, negative indicates forgetting.
        """
        return float(performance_after - performance_before)

    def compute_forward_transfer(
        self,
        new_task_performance: float,
        random_baseline: float = 0.0,
    ) -> float:
        """Compute forward transfer.
        
        Measures how well knowledge from previous tasks helps on new task.
        """
        return float(new_task_performance - random_baseline)

    def compute_catastrophic_forgetting_index(self) -> float:
        """Compute catastrophic forgetting index across all tasks.
        
        Returns value in [0, 1] where 0 = no forgetting, 1 = complete forgetting.
        """
        if not self._task_performances:
            return 0.0
        
        forgetting_scores = []
        
        for task_id, performances in self._task_performances.items():
            if len(performances) < 2:
                continue
            
            max_perf = max(performances)
            final_perf = performances[-1]
            
            if max_perf == 0:
                continue
            
            forgetting = (max_perf - final_perf) / max_perf
            forgetting_scores.append(max(0.0, forgetting))
        
        if not forgetting_scores:
            return 0.0
        
        return float(np.mean(forgetting_scores))

    def evaluate(
        self,
        real_embeddings: Iterable[float] | None = None,
        generated_embeddings: Iterable[float] | None = None,
    ) -> ContinualLearningMetrics:
        """Evaluate comprehensive continual learning metrics.
        
        Returns ContinualLearningMetrics with all computed values.
        """
        # FID score
        fid = 0.0
        if real_embeddings is not None and generated_embeddings is not None:
            fid = self.compute_fid_score(real_embeddings, generated_embeddings)
        
        # Retention rate (average across all tasks)
        retention_rates = [
            self.compute_retention_rate(task_id)
            for task_id in self._task_performances
        ]
        avg_retention = float(np.mean(retention_rates)) if retention_rates else 1.0
        
        # Backward transfer (average across tasks with multiple performances)
        backward_transfers = []
        for task_id, performances in self._task_performances.items():
            if len(performances) >= 2:
                bt = self.compute_backward_transfer(
                    task_id, performances[0], performances[-1]
                )
                backward_transfers.append(bt)
        avg_backward = float(np.mean(backward_transfers)) if backward_transfers else 0.0
        
        # Forward transfer (use average first performance as proxy)
        first_performances = [
            perfs[0] for perfs in self._task_performances.values() if perfs
        ]
        avg_forward = float(np.mean(first_performances)) if first_performances else 0.0
        
        # Catastrophic forgetting
        cf_index = self.compute_catastrophic_forgetting_index()
        
        return ContinualLearningMetrics(
            fid_score=fid,
            retention_rate=avg_retention,
            backward_transfer=avg_backward,
            forward_transfer=avg_forward,
            catastrophic_forgetting_index=cf_index,
        )


class SelfRewardingRL:
    """Self-rewarding mechanism for dynamic learning rate tuning.
    
    Implements SRDRL (Self-Rewarding Deep RL) for adaptive η tuning
    as recommended in audit (MDPI 2024/2025 reference).
    """

    def __init__(
        self,
        initial_lr: float = 3e-4,
        lr_min: float = 1e-5,
        lr_max: float = 1e-3,
        reward_window: int = 100,
    ) -> None:
        self.current_lr = initial_lr
        self.lr_min = lr_min
        self.lr_max = lr_max
        self.reward_window = reward_window
        self._reward_history: list[float] = []
        self._lr_history: list[float] = [initial_lr]

    def update_lr(self, reward: float, convergence_rate: float) -> float:
        """Dynamically adjust learning rate based on reward and convergence.
        
        Returns updated learning rate.
        """
        self._reward_history.append(reward)
        
        if len(self._reward_history) < 2:
            return self.current_lr
        
        # Compute reward trend
        recent_rewards = self._reward_history[-self.reward_window:]
        if len(recent_rewards) >= 2:
            reward_trend = recent_rewards[-1] - np.mean(recent_rewards[:-1])
        else:
            reward_trend = 0.0
        
        # Adjust learning rate
        if reward_trend > 0 and convergence_rate < 0:  # Improving but not converging
            # Increase LR to speed up
            self.current_lr = min(self.current_lr * 1.1, self.lr_max)
        elif reward_trend < 0:  # Degrading
            # Decrease LR to stabilize
            self.current_lr = max(self.current_lr * 0.9, self.lr_min)
        
        self._lr_history.append(self.current_lr)
        return self.current_lr

    def get_lr_schedule(self) -> list[float]:
        """Return learning rate history."""
        return self._lr_history.copy()


__all__ = [
    "ContinualLearningEvaluator",
    "ContinualLearningMetrics",
    "SelfRewardingRL",
]
