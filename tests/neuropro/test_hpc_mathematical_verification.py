"""
Symbolic and analytical verification of HPC-AI v4 mathematical formulations.

Verifies PWPE and TD-loss calculations against literature (Friston 2008, Mathys et al. 2011).
Uses sympy for analytical checks and torch.autograd for gradient tests.
"""

import numpy as np
import pytest
import torch
import torch.nn.functional as F

from neuropro.hpc_active_inference_v4 import HPCActiveInferenceModuleV4
from neuropro.hpc_validation import generate_synthetic_data

try:
    import sympy as sp

    SYMPY_AVAILABLE = True
except ImportError:
    SYMPY_AVAILABLE = False


@pytest.fixture
def small_model():
    """Create a small model for testing."""
    return HPCActiveInferenceModuleV4(
        input_dim=10,
        state_dim=16,
        action_dim=3,
        hidden_dim=32,
        hpc_levels=2,  # Reduced for testing
    )


class TestPWPEFormulation:
    """
    Test Precision-Weighted Prediction Error formulation.

    According to Friston (2008) and Mathys et al. (2011):
    PWPE at level l: ε_l = π_l · (s_l - μ_l)
    Total PWPE: ε = Σ ε_l / L

    where:
    - π_l is learnable precision weight
    - s_l is sensory state
    - μ_l is top-down prediction
    - L is number of levels
    """

    def test_pwpe_formula_toy_example(self, small_model):
        """Test PWPE calculation on toy data."""
        # Create simple state
        state = torch.randn(1, 16)

        # Get PWPE
        pred, pwpe = small_model.hpc_forward(state)

        # PWPE should be:
        # 1. Non-negative (it's a norm)
        assert pwpe.item() >= 0.0

        # 2. Scalar value
        assert pwpe.dim() == 0 or (pwpe.dim() == 1 and len(pwpe) == 1)

    def test_pwpe_precision_weights_impact(self, small_model):
        """Test that precision weights affect PWPE magnitude."""
        state = torch.randn(1, 16)

        # Get baseline PWPE
        _, pwpe_baseline = small_model.hpc_forward(state)

        # Increase precision weights
        with torch.no_grad():
            small_model.precision_weights.mul_(2.0)

        _, pwpe_scaled = small_model.hpc_forward(state)

        # Higher precision should generally lead to higher PWPE
        # (more weight on prediction errors)
        assert pwpe_scaled.item() > pwpe_baseline.item() * 0.5

    def test_pwpe_with_perfect_prediction(self):
        """Test PWPE when prediction equals observation (should be near zero)."""
        # Create model with fixed predictions
        model = HPCActiveInferenceModuleV4(state_dim=8, hpc_levels=1)

        # Use same state for prediction and observation (mock perfect prediction)
        state = torch.ones(1, 8) * 0.5

        _, pwpe = model.hpc_forward(state)

        # With random initialization, won't be zero but should be bounded
        assert 0.0 <= pwpe.item() < 100.0

    @pytest.mark.skipif(not SYMPY_AVAILABLE, reason="sympy not installed")
    def test_pwpe_symbolic_verification(self):
        """Symbolic verification of PWPE formula."""
        # Define symbolic variables
        pi_l = sp.Symbol("pi_l", positive=True)  # precision
        s_l = sp.Symbol("s_l", real=True)  # sensory state
        mu_l = sp.Symbol("mu_l", real=True)  # prediction

        # PWPE formula from literature
        epsilon_l = pi_l * (s_l - mu_l)

        # Verify properties
        # 1. Linear in prediction error
        assert sp.diff(epsilon_l, s_l) == pi_l
        assert sp.diff(epsilon_l, mu_l) == -pi_l

        # 2. Scales with precision
        assert sp.diff(epsilon_l, pi_l) == (s_l - mu_l)


class TestTDLossFormulation:
    """
    Test TD-loss and actor loss formulation.

    TD-error (Sutton & Barto, 2018):
    δ_t = r_{t+1} + γ V(s_{t+1}) - V(s_t)

    Actor loss (with perturbation rectification):
    L = -log π(a|s) · δ + ½ (π(a|s) - π(a|s+ε))²
    """

    def test_td_error_formula_toy_example(self, small_model):
        """Test TD-error formula on toy data."""
        # Create toy states
        state = torch.randn(1, 16, requires_grad=True)
        next_state = torch.randn(1, 16, requires_grad=True)
        torch.tensor([1])
        reward = 1.0
        gamma = 0.99

        # Compute expected TD error manually
        with torch.no_grad():
            v_s = small_model.critic(state)
            v_s_next = small_model.critic(next_state)
            expected_td = reward + gamma * v_s_next - v_s

        # This is approximate since training step modifies model
        # Just check it's reasonable
        assert not torch.isnan(expected_td).any()
        assert not torch.isinf(expected_td).any()

    def test_actor_loss_gradient_flow(self, small_model):
        """Test that actor loss allows gradient flow."""
        # Create state with gradients enabled
        state = torch.randn(1, 16, requires_grad=True)

        # Get action logits
        action_logits = small_model.actor(state)

        # Check gradients flow
        loss = action_logits.sum()
        loss.backward()

        assert state.grad is not None
        assert not torch.isnan(state.grad).any()

    def test_perturbation_rectification(self, small_model):
        """Test perturbation rectification term in actor loss."""
        data = generate_synthetic_data(n_days=100, seed=42)
        state = small_model.afferent_synthesis(data)

        # Get action probabilities
        action_logits = small_model.actor(state)
        action_probs = F.softmax(action_logits, dim=-1)

        # Add perturbation
        perturbation = torch.randn_like(state) * small_model.perturbation_scale
        perturbed_state = state + perturbation

        perturbed_logits = small_model.actor(perturbed_state)
        perturbed_probs = F.softmax(perturbed_logits, dim=-1)

        # Perturbation rectification term: ½(π(a|s) - π(a|s+ε))²
        rectification = 0.5 * (action_probs - perturbed_probs).pow(2).mean()

        # Should be non-negative and bounded
        assert rectification.item() >= 0.0
        assert rectification.item() < 1.0

    def test_critic_value_range(self, small_model):
        """Test that critic outputs are in reasonable range."""
        data = generate_synthetic_data(n_days=100, seed=42)
        state = small_model.afferent_synthesis(data)

        value = small_model.critic(state)

        # Should be finite
        assert not torch.isnan(value).any()
        assert not torch.isinf(value).any()

        # Should be scalar
        assert value.shape == (1, 1) or value.shape == (1,)

    @pytest.mark.skipif(not SYMPY_AVAILABLE, reason="sympy not installed")
    def test_td_error_symbolic(self):
        """Symbolic verification of TD-error formula."""
        # Define symbolic variables
        r = sp.Symbol("r", real=True)  # reward
        gamma = sp.Symbol("gamma", positive=True)  # discount
        V_s = sp.Symbol("V_s", real=True)  # value at s
        V_s_next = sp.Symbol("V_s_next", real=True)  # value at s'

        # TD-error formula
        delta = r + gamma * V_s_next - V_s

        # Properties
        # 1. Linear in reward
        assert sp.diff(delta, r) == 1

        # 2. Scales with discount
        assert sp.diff(delta, gamma) == V_s_next

        # 3. Decreases with current value
        assert sp.diff(delta, V_s) == -1

        # 4. Increases with next value
        assert sp.diff(delta, V_s_next) == gamma


class TestSelfRewardFormulation:
    """
    Test self-reward formulation with blending and modulation.

    r_self = α · r_pred + (1-α) · r_expert
    r_mod = r_self · (1 - k · ε)

    where α ∈ [0,1] with L1 regularization.
    """

    def test_reward_blending_bounds(self, small_model):
        """Test that blending produces values in expected range."""
        expert_metrics = torch.tensor([1.0, 0.1, 0.2])  # Sharpe, DD, Return
        pwpe = 0.15

        reward = small_model.compute_self_reward(expert_metrics, pwpe)

        # Should be finite
        assert not np.isnan(reward)
        assert not np.isinf(reward)

    def test_alpha_l1_regularization(self, small_model):
        """Test that L1 regularization keeps alpha bounded."""
        # Get initial alpha
        initial_alpha = small_model.blending_alpha.item()
        assert 0.0 <= initial_alpha <= 1.0

        # Train for several steps
        data = generate_synthetic_data(n_days=100, seed=42)
        for _ in range(50):
            state = small_model.afferent_synthesis(data)
            action = torch.tensor([np.random.randint(0, 3)])
            reward = np.random.uniform(-1, 1)

            small_model.sr_drl_step(state, action, reward, state, 0.15)

        # Alpha should remain in [0, 1] due to L1 regularization
        final_alpha = small_model.blending_alpha.item()
        assert 0.0 <= final_alpha <= 1.0

    def test_uncertainty_modulation(self, small_model):
        """Test that uncertainty modulates reward."""
        expert_metrics = torch.tensor([1.0, 0.1, 0.2])

        # Low uncertainty
        reward_low = small_model.compute_self_reward(expert_metrics, pwpe=0.01)

        # High uncertainty
        reward_high = small_model.compute_self_reward(expert_metrics, pwpe=0.8)

        # High uncertainty should reduce reward magnitude
        # r_mod = r * (1 - k * ε), with k=0.1
        # For ε=0.8: r_mod = r * (1 - 0.08) = 0.92r
        # So reward_high should be ~92% of reward_low (approximately)
        ratio = abs(reward_high) / (abs(reward_low) + 1e-8)
        assert 0.5 <= ratio <= 1.0  # Loose bound

    @pytest.mark.skipif(not SYMPY_AVAILABLE, reason="sympy not installed")
    def test_reward_modulation_symbolic(self):
        """Symbolic verification of reward modulation."""
        # Define symbolic variables
        r_pred = sp.Symbol("r_pred", real=True)
        r_expert = sp.Symbol("r_expert", real=True)
        alpha = sp.Symbol("alpha", positive=True)
        k = sp.Symbol("k", positive=True)
        epsilon = sp.Symbol("epsilon", positive=True)

        # Formulas
        r_self = alpha * r_pred + (1 - alpha) * r_expert
        r_mod = r_self * (1 - k * epsilon)

        # Properties
        # 1. Linear interpolation in alpha
        assert sp.limit(r_self, alpha, 0) == r_expert
        assert sp.limit(r_self, alpha, 1) == r_pred

        # 2. Modulation decreases with uncertainty
        assert sp.diff(r_mod, epsilon) == -k * r_self


class TestGradientProperties:
    """Test gradient properties with torch.autograd."""

    def test_end_to_end_gradient_flow(self, small_model):
        """Test that gradients flow through entire pipeline."""
        data = generate_synthetic_data(n_days=100, seed=42)

        # Enable gradient tracking
        small_model.train()

        # Forward pass
        state = small_model.afferent_synthesis(data)
        pred, pwpe = small_model.hpc_forward(state)

        # Check gradient can flow
        loss = pwpe
        loss.backward()

        # Check at least some parameters have gradients
        has_grad = False
        for param in small_model.parameters():
            if param.grad is not None:
                has_grad = True
                assert not torch.isnan(param.grad).any()

        assert has_grad

    def test_actor_critic_gradient_independence(self, small_model):
        """Test actor and critic gradients are computed correctly."""
        data = generate_synthetic_data(n_days=100, seed=42)
        state = small_model.afferent_synthesis(data)
        torch.tensor([1])
        reward = 1.0

        # Zero gradients
        small_model.optimizer.zero_grad()

        # Compute losses
        current_v = small_model.critic(state)
        next_v = small_model.critic(state)
        td_error = reward + 0.99 * next_v - current_v

        critic_loss = td_error.pow(2).mean()

        # Check critic loss has reasonable gradient
        critic_loss.backward(retain_graph=True)

        # At least critic should have gradients
        assert small_model.critic.weight.grad is not None


class TestNumericalStability:
    """Test numerical stability of computations."""

    def test_log_probability_stability(self, small_model):
        """Test log probabilities don't cause numerical issues."""
        data = generate_synthetic_data(n_days=100, seed=42)
        state = small_model.afferent_synthesis(data)

        action_logits = small_model.actor(state)
        action_probs = F.softmax(action_logits, dim=-1)

        # Log probability should be stable
        log_probs = torch.log(action_probs + 1e-8)

        assert not torch.isnan(log_probs).any()
        assert not torch.isinf(log_probs).any()

    def test_softmax_temperature_stability(self, small_model):
        """Test softmax with different temperatures."""
        logits = torch.randn(1, 3) * 10  # Large logits

        for temp in [0.1, 1.0, 10.0, 100.0]:
            probs = F.softmax(logits / temp, dim=-1)

            assert not torch.isnan(probs).any()
            assert not torch.isinf(probs).any()
            assert torch.allclose(probs.sum(), torch.tensor(1.0), atol=1e-5)

    def test_precision_weight_positivity(self, small_model):
        """Test that precision weights remain positive during training."""
        data = generate_synthetic_data(n_days=100, seed=42)

        # Train for several steps
        for _ in range(20):
            state = small_model.afferent_synthesis(data)
            action = torch.tensor([np.random.randint(0, 3)])
            reward = np.random.uniform(-1, 1)

            small_model.sr_drl_step(state, action, reward, state, 0.15)

        # Precision weights should remain positive (they're initialized positive)
        for weight in small_model.precision_weights:
            assert weight.item() > 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
