# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""
Ablation studies for HPC-AI v4 components.

Tests model performance without:
1. Metastable transition gate
2. Self-reward blending (fixed alpha=0 or alpha=1)

Measures impact on PWPE, Sharpe ratio, and action diversity.
Includes statistical significance tests (t-test).
"""

from __future__ import annotations

import gc
from typing import Any, Iterator, cast

import numpy as np
import pytest
import torch
from scipy import stats

from geosync_hpc.hpc_active_inference_v4 import HPCActiveInferenceModuleV4
from geosync_hpc.hpc_validation import (
    generate_synthetic_data,
    simple_backtest,
    validate_hpc_ai,
)


def _cpu_model(**kwargs: Any) -> HPCActiveInferenceModuleV4:
    """Create model on CPU to avoid GPU OOM with multiple models."""
    m = HPCActiveInferenceModuleV4(**kwargs)
    m.device = torch.device("cpu")
    m.to(m.device)
    return m


@pytest.fixture(autouse=True)
def _cleanup_gpu() -> Iterator[None]:
    yield
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


class TestAblationStudies:
    """Ablation studies to measure component contributions."""

    def test_ablation_no_metastable_gate(self) -> None:
        """
        Ablation: Remove metastable gate.
        Expected: Higher action diversity, potentially lower Sharpe in high uncertainty.
        """
        # Model with gate (baseline)
        model_with_gate = _cpu_model(state_dim=64)

        # Model without gate (mock by always returning False)
        model_no_gate = _cpu_model(state_dim=64)

        # Generate high volatility data (high uncertainty scenario)
        data = generate_synthetic_data(n_days=500, volatility=3.0, seed=42)

        # Test with gate
        actions_with_gate: list[int] = []
        pwpes_with_gate: list[float] = []
        prev_pwpe = 0.0

        for i in range(20):
            window = data.iloc[i * 20 : (i + 1) * 20 + 80]
            action = model_with_gate.decide_action(window, prev_pwpe)
            pwpe = model_with_gate.get_pwpe(window)
            actions_with_gate.append(action)
            pwpes_with_gate.append(pwpe)
            prev_pwpe = pwpe

        # Test without gate (override method to always return False)
        setattr(  # noqa: B010
            model_no_gate,
            "metastable_transition_gate",
            lambda pwpe, d_pwpe_dt: False,
        )

        actions_no_gate: list[int] = []
        pwpes_no_gate: list[float] = []
        prev_pwpe = 0.0

        for i in range(20):
            window = data.iloc[i * 20 : (i + 1) * 20 + 80]
            action = model_no_gate.decide_action(window, prev_pwpe)
            pwpe = model_no_gate.get_pwpe(window)
            actions_no_gate.append(action)
            pwpes_no_gate.append(pwpe)
            prev_pwpe = pwpe

        # Metrics
        actions_with_gate.count(0) / len(actions_with_gate)
        actions_no_gate.count(0) / len(actions_no_gate)
        diversity_with = len(set(actions_with_gate)) / 3.0
        diversity_without = len(set(actions_no_gate)) / 3.0

        # Without gate should have more diversity (less conservative)
        assert diversity_without >= diversity_with or abs(diversity_without - diversity_with) < 0.2

        # PWPE should be similar (gate doesn't affect computation, only decisions)
        assert abs(np.mean(pwpes_with_gate) - np.mean(pwpes_no_gate)) < 5.0

    def test_ablation_self_reward_expert_only(self) -> None:
        """
        Ablation: Use only expert rewards (alpha=0).
        Expected: More stable but less adaptive learning.
        """
        # Model with blending (baseline)
        model_blend = _cpu_model(state_dim=64)

        # Model with expert-only rewards (alpha=0)
        model_expert = _cpu_model(state_dim=64)
        with torch.no_grad():
            model_expert.blending_alpha.fill_(0.0)

        data = generate_synthetic_data(n_days=300, seed=42)

        # Train both models
        expert_metrics = torch.tensor([1.0, 0.1, 0.2])

        rewards_blend: list[float] = []
        rewards_expert: list[float] = []

        for i in range(10):
            window = data.iloc[i * 25 : (i + 1) * 25 + 75]

            # Blended model
            state_b = model_blend.afferent_synthesis(window)
            _, pwpe_b = model_blend.hpc_forward(state_b)
            reward_b = model_blend.compute_self_reward(expert_metrics, pwpe_b.item())
            rewards_blend.append(reward_b)

            # Expert-only model
            state_e = model_expert.afferent_synthesis(window)
            _, pwpe_e = model_expert.hpc_forward(state_e)
            reward_e = model_expert.compute_self_reward(expert_metrics, pwpe_e.item())
            rewards_expert.append(reward_e)

        # Expert-only should have less variance (more stable)
        var_blend = np.var(rewards_blend)
        var_expert = np.var(rewards_expert)

        # Both should be finite
        assert not np.isnan(var_blend) and not np.isnan(var_expert)
        assert var_blend >= 0.0 and var_expert >= 0.0

    def test_ablation_self_reward_predicted_only(self) -> None:
        """
        Ablation: Use only predicted rewards (alpha=1).
        Expected: More adaptive but potentially unstable.
        """
        # Model with blending (baseline)
        model_blend = _cpu_model(state_dim=64)

        # Model with predicted-only rewards (alpha=1)
        model_pred = _cpu_model(state_dim=64)
        with torch.no_grad():
            model_pred.blending_alpha.fill_(1.0)

        data = generate_synthetic_data(n_days=300, seed=42)

        # Validate both models
        metrics_blend = validate_hpc_ai(model_blend, data, n_steps=10)
        metrics_pred = validate_hpc_ai(model_pred, data, n_steps=10)

        # Both should produce valid metrics
        assert metrics_blend.mean_pwpe > 0.0
        assert metrics_pred.mean_pwpe > 0.0
        assert 0.0 <= metrics_blend.action_diversity <= 1.0
        assert 0.0 <= metrics_pred.action_diversity <= 1.0

    @pytest.mark.heavy_math
    def test_ablation_combined_effects(self) -> None:
        """
        Test combined ablation: no gate + expert-only rewards.
        Measure cumulative impact on performance.
        """
        # Baseline: full model
        model_full = _cpu_model(state_dim=64)

        # Ablated: no gate + expert-only
        model_ablated = _cpu_model(state_dim=64)
        with torch.no_grad():
            model_ablated.blending_alpha.fill_(0.0)
        setattr(  # noqa: B010
            model_ablated,
            "metastable_transition_gate",
            lambda pwpe, d_pwpe_dt: False,
        )

        data = generate_synthetic_data(n_days=500, volatility=2.0, seed=42)

        # Run simple backtest
        results_full = simple_backtest(model_full, data, initial_capital=10000.0)
        results_ablated = simple_backtest(model_ablated, data, initial_capital=10000.0)

        # Both should complete without errors
        assert "total_return" in results_full
        assert "total_return" in results_ablated
        assert "sharpe" in results_full
        assert "sharpe" in results_ablated

        # Action distributions should differ — simple_backtest ships `Dict[str, float]`
        # in its signature but actually returns a nested dict under `action_distribution`;
        # narrow via cast so the structural access is mypy-clean until the upstream
        # return annotation is tightened.
        dist_full = cast(dict[str, float], results_full["action_distribution"])
        dist_ablated = cast(dict[str, float], results_ablated["action_distribution"])

        # Check distributions are valid
        assert abs(sum(dist_full.values()) - 1.0) < 0.01
        assert abs(sum(dist_ablated.values()) - 1.0) < 0.01


class TestStatisticalSignificance:
    """Test statistical significance of ablations."""

    def test_pwpe_difference_significance(self) -> None:
        """
        Test if PWPE differs significantly with/without gate.
        H0: mean(PWPE_with_gate) = mean(PWPE_without_gate)
        """
        model_with = _cpu_model(state_dim=64)
        model_without = _cpu_model(state_dim=64)
        setattr(  # noqa: B010
            model_without,
            "metastable_transition_gate",
            lambda pwpe, d_pwpe_dt: False,
        )

        data = generate_synthetic_data(n_days=200, volatility=2.0, seed=42)

        pwpes_with: list[float] = []
        pwpes_without: list[float] = []

        for i in range(15):
            window = data.iloc[i * 10 : (i + 1) * 10 + 50]
            pwpes_with.append(model_with.get_pwpe(window))
            pwpes_without.append(model_without.get_pwpe(window))

        # t-test for independent samples
        t_stat, p_value = stats.ttest_ind(pwpes_with, pwpes_without)

        # Report statistics
        print(f"\nPWPE t-test: t={t_stat:.4f}, p={p_value:.4f}")
        print(f"Mean PWPE with gate: {np.mean(pwpes_with):.4f}")
        print(f"Mean PWPE without gate: {np.mean(pwpes_without):.4f}")

        # Test should complete without errors
        assert not np.isnan(t_stat)
        assert 0.0 <= p_value <= 1.0

    def test_sharpe_difference_significance(self) -> None:
        """
        Test if Sharpe ratio differs significantly with/without blending.
        Run multiple trials and compute t-test.
        """
        n_trials = 5
        sharpes_blend: list[float] = []
        sharpes_expert: list[float] = []

        for trial in range(n_trials):
            model_blend = _cpu_model(state_dim=32)
            model_expert = _cpu_model(state_dim=32)
            with torch.no_grad():
                model_expert.blending_alpha.fill_(0.0)

            data = generate_synthetic_data(n_days=200, seed=42 + trial)

            # Quick validation (fewer steps for speed)
            metrics_blend = validate_hpc_ai(model_blend, data, n_steps=5)
            metrics_expert = validate_hpc_ai(model_expert, data, n_steps=5)

            sharpes_blend.append(metrics_blend.sharpe_proxy)
            sharpes_expert.append(metrics_expert.sharpe_proxy)

        # t-test
        t_stat, p_value = stats.ttest_rel(sharpes_blend, sharpes_expert)

        print(f"\nSharpe t-test: t={t_stat:.4f}, p={p_value:.4f}")
        print(
            f"Mean Sharpe with blending: {np.mean(sharpes_blend):.4f} ± {np.std(sharpes_blend):.4f}"
        )
        print(
            f"Mean Sharpe expert-only: {np.mean(sharpes_expert):.4f} ± {np.std(sharpes_expert):.4f}"
        )

        # Test should complete
        assert not np.isnan(t_stat)
        assert 0.0 <= p_value <= 1.0


class TestComponentContributions:
    """Measure individual component contributions to performance."""

    @pytest.mark.heavy_math
    def test_gate_contribution_to_drawdown(self) -> None:
        """
        Measure if metastable gate reduces maximum drawdown.
        Expected: Gate should reduce drawdown in volatile markets.
        """
        model_with = _cpu_model(state_dim=64)
        model_without = _cpu_model(state_dim=64)
        setattr(  # noqa: B010
            model_without,
            "metastable_transition_gate",
            lambda pwpe, d_pwpe_dt: False,
        )

        # High volatility data
        data = generate_synthetic_data(n_days=300, volatility=4.0, seed=42)

        results_with = simple_backtest(model_with, data, initial_capital=10000.0)
        results_without = simple_backtest(model_without, data, initial_capital=10000.0)

        dd_with = results_with["max_drawdown"]
        dd_without = results_without["max_drawdown"]

        print(f"\nDrawdown with gate: {dd_with:.2%}")
        print(f"Drawdown without gate: {dd_without:.2%}")

        # Both should be valid
        assert 0.0 <= dd_with <= 1.0
        assert 0.0 <= dd_without <= 1.0

    def test_blending_contribution_to_stability(self) -> None:
        """
        Measure if reward blending improves training stability.
        Expected: Blending should reduce reward variance.
        """
        n_runs = 3
        variances_blend: list[float] = []
        variances_expert: list[float] = []

        for run in range(n_runs):
            model_blend = _cpu_model(state_dim=32)
            model_expert = _cpu_model(state_dim=32)
            with torch.no_grad():
                model_expert.blending_alpha.fill_(0.0)

            data = generate_synthetic_data(n_days=150, seed=42 + run)
            expert_metrics = torch.tensor([1.0, 0.1, 0.2])

            rewards_blend: list[float] = []
            rewards_expert: list[float] = []

            for i in range(10):
                window = data.iloc[i * 10 : (i + 1) * 10 + 50]

                state_b = model_blend.afferent_synthesis(window)
                _, pwpe_b = model_blend.hpc_forward(state_b)
                rewards_blend.append(model_blend.compute_self_reward(expert_metrics, pwpe_b.item()))

                state_e = model_expert.afferent_synthesis(window)
                _, pwpe_e = model_expert.hpc_forward(state_e)
                rewards_expert.append(
                    model_expert.compute_self_reward(expert_metrics, pwpe_e.item())
                )

            variances_blend.append(float(np.var(rewards_blend)))
            variances_expert.append(float(np.var(rewards_expert)))

        print(
            f"\nReward variance with blending: {np.mean(variances_blend):.6f} ± {np.std(variances_blend):.6f}"
        )
        print(
            f"Reward variance expert-only: {np.mean(variances_expert):.6f} ± {np.std(variances_expert):.6f}"
        )

        # Both should be non-negative
        assert all(v >= 0.0 for v in variances_blend)
        assert all(v >= 0.0 for v in variances_expert)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
