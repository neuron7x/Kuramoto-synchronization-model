"""
Tests for HPC-AI v4 module.
"""

import pytest
import torch
import torch.nn.functional as F
import pandas as pd
import numpy as np
from neuropro.hpc_active_inference_v4 import HPCActiveInferenceModuleV4
from neuropro.hpc_validation import (
    generate_synthetic_data,
    calibrate_perturbation_scale,
    validate_hpc_ai,
    simple_backtest,
    format_validation_report,
)


@pytest.fixture
def synthetic_data():
    """Generate synthetic market data."""
    return generate_synthetic_data(n_days=200, seed=42)


@pytest.fixture
def hpc_ai_model():
    """Create HPC-AI model instance."""
    return HPCActiveInferenceModuleV4(
        input_dim=10,
        state_dim=64,  # Smaller for faster tests
        action_dim=3,
        hidden_dim=128,
        hpc_levels=3,
        learning_rate=1e-4,
    )


class TestHPCActiveInferenceModule:
    """Test HPC-AI module components."""

    def test_initialization(self, hpc_ai_model):
        """Test model initialization."""
        assert hpc_ai_model.input_dim == 10
        assert hpc_ai_model.state_dim == 64
        assert hpc_ai_model.action_dim == 3
        assert hpc_ai_model.hpc_levels == 3

        # Check parameter initialization
        assert abs(hpc_ai_model.blending_alpha.item() - 0.5) < 1e-5
        assert abs(hpc_ai_model.perturbation_scale.item() - 0.01) < 1e-5
        assert abs(hpc_ai_model.pwpe_threshold_base.item() - 0.2) < 1e-5

    def test_afferent_synthesis(self, hpc_ai_model, synthetic_data):
        """Test afferent synthesis module."""
        state = hpc_ai_model.afferent_synthesis(synthetic_data)

        assert isinstance(state, torch.Tensor)
        assert state.shape == (1, 64)
        assert not torch.isnan(state).any()
        assert not torch.isinf(state).any()

    def test_hpc_forward(self, hpc_ai_model, synthetic_data):
        """Test hierarchical predictive coding forward pass."""
        state = hpc_ai_model.afferent_synthesis(synthetic_data)
        pred, pwpe = hpc_ai_model.hpc_forward(state)

        assert isinstance(pred, torch.Tensor)
        assert isinstance(pwpe, torch.Tensor)
        assert pwpe.item() >= 0.0
        assert not torch.isnan(pwpe).any()

    def test_compute_self_reward(self, hpc_ai_model):
        """Test self-reward computation."""
        expert_metrics = torch.tensor([1.5, 0.05, 0.12])  # Sharpe, DD, Return
        pwpe = 0.15

        reward = hpc_ai_model.compute_self_reward(expert_metrics, pwpe)

        assert isinstance(reward, float)
        assert not np.isnan(reward)
        assert not np.isinf(reward)

    def test_sr_drl_step(self, hpc_ai_model, synthetic_data):
        """Test self-rewarding deep RL step."""
        state = hpc_ai_model.afferent_synthesis(synthetic_data)
        action = torch.tensor([1])  # Buy
        next_state = state
        pwpe = 0.15
        expert_metrics = torch.tensor([1.5, 0.05, 0.12])
        reward = hpc_ai_model.compute_self_reward(expert_metrics, pwpe)

        td_error = hpc_ai_model.sr_drl_step(
            state,
            action,
            reward,
            expert_metrics,
            next_state,
            pwpe,
        )

        assert isinstance(td_error, float)
        assert not np.isnan(td_error)
        assert not np.isinf(td_error)

    def test_reward_predictor_improves_with_metrics(
        self, hpc_ai_model, synthetic_data
    ):
        """Reward predictor loss should decrease when metrics accompany rewards."""
        action = torch.tensor([1])
        pwpe = 0.1
        expert_metrics = torch.tensor([0.8, 0.05, 0.12], dtype=torch.float32)
        reward = hpc_ai_model.compute_self_reward(expert_metrics, pwpe)

        metrics_tensor = expert_metrics.to(hpc_ai_model.device).unsqueeze(0)
        target_reward = torch.tensor(
            [[reward]], dtype=torch.float32, device=hpc_ai_model.device
        )

        with torch.no_grad():
            initial_pred = hpc_ai_model.reward_predictor(metrics_tensor)
            initial_loss = F.mse_loss(initial_pred, target_reward).item()

        for _ in range(5):
            state = hpc_ai_model.afferent_synthesis(synthetic_data).detach()
            next_state = state
            hpc_ai_model.sr_drl_step(
                state,
                action,
                reward,
                expert_metrics,
                next_state,
                pwpe,
            )

        with torch.no_grad():
            final_pred = hpc_ai_model.reward_predictor(metrics_tensor)
            final_loss = F.mse_loss(final_pred, target_reward).item()

        assert final_loss < initial_loss

    def test_sr_drl_step_requires_metrics(self, hpc_ai_model, synthetic_data):
        """Ensure SR-DRL training fails when expert metrics are omitted."""
        state = hpc_ai_model.afferent_synthesis(synthetic_data)
        action = torch.tensor([0])
        next_state = state
        pwpe = 0.1

        with pytest.raises(ValueError):
            hpc_ai_model.sr_drl_step(state, action, 0.1, None, next_state, pwpe)

    def test_metastable_transition_gate(self, hpc_ai_model):
        """Test metastable transition gate."""
        # Low PWPE, low change -> should not trigger
        gate1 = hpc_ai_model.metastable_transition_gate(0.1, 0.01)
        
        # High PWPE, high change -> may trigger
        gate2 = hpc_ai_model.metastable_transition_gate(0.5, 0.3)

        assert isinstance(gate1, bool)
        assert isinstance(gate2, bool)

    def test_gumbel_softmax_sample(self, hpc_ai_model):
        """Test Gumbel-Softmax sampling."""
        logits = torch.randn(1, 3)

        # Hard sampling
        sample_hard = hpc_ai_model.gumbel_softmax_sample(logits, hard=True)
        assert sample_hard.shape == (1, 3)
        assert torch.allclose(sample_hard.sum(), torch.tensor(1.0))

        # Soft sampling
        sample_soft = hpc_ai_model.gumbel_softmax_sample(logits, hard=False)
        assert sample_soft.shape == (1, 3)
        assert torch.allclose(sample_soft.sum(), torch.tensor(1.0), atol=1e-5)

    def test_decide_action(self, hpc_ai_model, synthetic_data):
        """Test action decision."""
        action = hpc_ai_model.decide_action(synthetic_data, prev_pwpe=0.0)

        assert isinstance(action, int)
        assert action in [0, 1, 2]  # Hold, Buy, Sell

    def test_get_state_representation(self, hpc_ai_model, synthetic_data):
        """Test getting state representation."""
        state = hpc_ai_model.get_state_representation(synthetic_data)

        assert isinstance(state, torch.Tensor)
        assert state.shape == (1, 64)

    def test_get_pwpe(self, hpc_ai_model, synthetic_data):
        """Test getting PWPE value."""
        pwpe = hpc_ai_model.get_pwpe(synthetic_data)

        assert isinstance(pwpe, float)
        assert pwpe >= 0.0


class TestValidationUtils:
    """Test validation and calibration utilities."""

    def test_generate_synthetic_data(self):
        """Test synthetic data generation."""
        data = generate_synthetic_data(n_days=100, seed=42)

        assert len(data) == 100
        assert isinstance(data.index, pd.DatetimeIndex)
        assert all(col in data.columns for col in ["open", "high", "low", "close", "volume"])
        
        # Check OHLC constraints
        assert (data["high"] >= data["low"]).all()
        assert (data["high"] >= data["open"]).all()
        assert (data["high"] >= data["close"]).all()
        assert (data["low"] <= data["open"]).all()
        assert (data["low"] <= data["close"]).all()

    def test_calibrate_perturbation_scale(self, hpc_ai_model, synthetic_data):
        """Test perturbation scale calibration."""
        best_epsilon, results = calibrate_perturbation_scale(
            hpc_ai_model,
            synthetic_data,
            epsilon_grid=[0.005, 0.01],
            n_steps=3,
        )

        assert best_epsilon in [0.005, 0.01]
        assert len(results) == 2
        assert all(isinstance(v, float) for v in results.values())

    def test_validate_hpc_ai(self, hpc_ai_model, synthetic_data):
        """Test HPC-AI validation."""
        metrics = validate_hpc_ai(hpc_ai_model, synthetic_data, n_steps=5)

        assert metrics.mean_pwpe >= 0.0
        assert metrics.std_pwpe >= 0.0
        assert 0.0 <= metrics.action_diversity <= 1.0
        assert metrics.sharpe_proxy >= 0.0
        assert 0.0 <= metrics.final_alpha <= 1.0
        assert metrics.final_sigma > 0.0
        assert metrics.final_beta > 0.0

    def test_simple_backtest(self, hpc_ai_model, synthetic_data):
        """Test simple backtest."""
        results = simple_backtest(
            hpc_ai_model,
            synthetic_data,
            initial_capital=10000.0,
        )

        assert "total_return" in results
        assert "sharpe" in results
        assert "max_drawdown" in results
        assert "n_trades" in results
        assert "mean_pwpe" in results
        assert "final_capital" in results
        assert "action_distribution" in results

        # Check action distribution sums to ~1
        dist = results["action_distribution"]
        total_dist = dist["hold"] + dist["buy"] + dist["sell"]
        assert 0.99 <= total_dist <= 1.01

    def test_format_validation_report(self, hpc_ai_model, synthetic_data):
        """Test validation report formatting."""
        metrics = validate_hpc_ai(hpc_ai_model, synthetic_data, n_steps=3)
        backtest_results = simple_backtest(hpc_ai_model, synthetic_data)

        report = format_validation_report(metrics, backtest_results)

        assert isinstance(report, str)
        assert "Validation Metrics" in report
        assert "Backtest Results" in report
        assert "Mean PWPE" in report
        assert "Sharpe" in report


class TestIntegration:
    """Integration tests."""

    def test_full_pipeline(self, hpc_ai_model, synthetic_data):
        """Test full HPC-AI pipeline."""
        prev_pwpe = 0.0
        actions = []
        pwpes = []

        # Run multiple steps
        for i in range(5):
            window_data = synthetic_data.iloc[i * 20 : (i + 1) * 20 + 80]
            
            action = hpc_ai_model.decide_action(window_data, prev_pwpe)
            actions.append(action)
            
            pwpe = hpc_ai_model.get_pwpe(window_data)
            pwpes.append(pwpe)
            
            prev_pwpe = pwpe

        # Validate results
        assert len(actions) == 5
        assert len(pwpes) == 5
        assert all(a in [0, 1, 2] for a in actions)
        assert all(p >= 0.0 for p in pwpes)

    def test_parameter_updates(self, hpc_ai_model, synthetic_data):
        """Test that parameters are updated during training."""
        initial_alpha = hpc_ai_model.blending_alpha.item()
        initial_precision = hpc_ai_model.precision_weights[0].item()

        # Run training steps
        for _ in range(10):
            state = hpc_ai_model.afferent_synthesis(synthetic_data)
            action = torch.tensor([1])
            next_state = state
            pwpe = 0.15
            expert_metrics = torch.tensor([0.9, 0.07, 0.11], dtype=torch.float32)
            reward = hpc_ai_model.compute_self_reward(expert_metrics, pwpe)

            hpc_ai_model.sr_drl_step(
                state, action, reward, expert_metrics, next_state, pwpe
            )

        final_alpha = hpc_ai_model.blending_alpha.item()
        final_precision = hpc_ai_model.precision_weights[0].item()

        # Parameters should have changed
        assert initial_alpha != final_alpha or initial_precision != final_precision


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
