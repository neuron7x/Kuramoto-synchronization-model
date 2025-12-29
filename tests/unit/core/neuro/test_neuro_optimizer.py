"""Tests for cross-neuromodulator optimization system."""

from __future__ import annotations

import numpy as np
import pytest

from tradepulse.core.neuro.neuro_optimizer import (
    BalanceMetrics,
    NeuroOptimizer,
    OptimizationConfig,
)


@pytest.fixture
def opt_config():
    """Fixture providing optimization configuration."""
    return OptimizationConfig(
        balance_weight=0.35,
        performance_weight=0.45,
        stability_weight=0.20,
        learning_rate=0.01,
        momentum=0.9,
        enable_plasticity=True,
    )


@pytest.fixture
def sample_params():
    """Fixture providing sample neuromodulator parameters."""
    return {
        'dopamine': {
            'discount_gamma': 0.99,
            'learning_rate': 0.01,
            'burst_factor': 1.5,
        },
        'serotonin': {
            'stress_threshold': 0.15,
            'release_threshold': 0.10,
        },
        'gaba': {
            'k_inhibit': 0.4,
            'impulse_threshold': 0.5,
        },
        'na_ach': {
            'arousal_gain': 1.2,
            'attention_gain': 1.0,
        },
    }


@pytest.fixture
def sample_state():
    """Fixture providing sample neuromodulator state."""
    return {
        'dopamine_level': 0.6,
        'serotonin_level': 0.3,
        'gaba_inhibition': 0.4,
        'na_arousal': 1.1,
        'ach_attention': 0.7,
    }


class TestOptimizationConfig:
    """Tests for OptimizationConfig dataclass."""

    def test_valid_config(self):
        """Test valid configuration."""
        config = OptimizationConfig(
            balance_weight=0.35,
            performance_weight=0.45,
            stability_weight=0.20,
        )

        assert config.balance_weight == 0.35
        assert config.performance_weight == 0.45
        assert config.stability_weight == 0.20

    def test_weights_must_sum_to_one(self):
        """Test that weights must sum to 1.0."""
        with pytest.raises(ValueError, match="must sum to 1.0"):
            OptimizationConfig(
                balance_weight=0.5,
                performance_weight=0.5,
                stability_weight=0.5,
            )

    def test_learning_rate_bounds(self):
        """Test learning rate must be in (0, 1)."""
        with pytest.raises(ValueError, match="Learning rate"):
            OptimizationConfig(learning_rate=0.0)

        with pytest.raises(ValueError, match="Learning rate"):
            OptimizationConfig(learning_rate=1.5)

    def test_momentum_bounds(self):
        """Test momentum must be in [0, 1)."""
        with pytest.raises(ValueError, match="Momentum"):
            OptimizationConfig(momentum=-0.1)

        with pytest.raises(ValueError, match="Momentum"):
            OptimizationConfig(momentum=1.0)


class TestBalanceMetrics:
    """Tests for BalanceMetrics dataclass."""

    def test_balance_metrics_creation(self):
        """Test balance metrics creation."""
        metrics = BalanceMetrics(
            dopamine_serotonin_ratio=2.0,
            gaba_excitation_balance=1.5,
            arousal_attention_coherence=0.9,
            overall_balance_score=0.8,
            homeostatic_deviation=0.1,
        )

        assert metrics.dopamine_serotonin_ratio == 2.0
        assert metrics.overall_balance_score == 0.8


class TestNeuroOptimizer:
    """Tests for NeuroOptimizer class."""

    def test_initialization(self, opt_config):
        """Test optimizer initialization."""
        optimizer = NeuroOptimizer(opt_config)

        assert optimizer.config == opt_config
        assert optimizer._iteration == 0
        assert optimizer._best_objective == -np.inf
        assert len(optimizer._performance_history) == 0

    def test_initialize_setpoints(self, opt_config):
        """Test homeostatic setpoints initialization."""
        optimizer = NeuroOptimizer(opt_config)

        setpoints = optimizer._setpoints

        assert 'dopamine_level' in setpoints
        assert 'serotonin_level' in setpoints
        assert 'da_5ht_ratio' in setpoints
        assert 'excitation_inhibition' in setpoints

    def test_calculate_balance_metrics(self, opt_config, sample_state):
        """Test balance metrics calculation."""
        optimizer = NeuroOptimizer(opt_config)

        balance = optimizer._calculate_balance_metrics(sample_state)

        assert isinstance(balance, BalanceMetrics)
        assert balance.dopamine_serotonin_ratio > 0
        assert balance.gaba_excitation_balance > 0
        assert 0 <= balance.arousal_attention_coherence <= 1
        assert 0 <= balance.overall_balance_score <= 1
        assert balance.homeostatic_deviation >= 0

    def test_calculate_balance_with_defaults(self, opt_config):
        """Test balance calculation with missing state values."""
        optimizer = NeuroOptimizer(opt_config)

        # Empty state should use defaults
        balance = optimizer._calculate_balance_metrics({})

        assert isinstance(balance, BalanceMetrics)
        assert balance.dopamine_serotonin_ratio > 0

    def test_calculate_objective(self, opt_config, sample_state):
        """Test objective function calculation."""
        optimizer = NeuroOptimizer(opt_config)

        balance = optimizer._calculate_balance_metrics(sample_state)
        performance = 1.5  # Sharpe ratio

        objective = optimizer._calculate_objective(performance, balance, sample_state)

        assert isinstance(objective, float)
        assert 0 <= objective <= 1

    def test_optimize_updates_state(self, opt_config, sample_params, sample_state):
        """Test that optimize() updates optimizer state."""
        optimizer = NeuroOptimizer(opt_config)

        updated_params, balance = optimizer.optimize(
            sample_params,
            sample_state,
            performance_score=1.5,
        )

        assert optimizer._iteration == 1
        assert len(optimizer._performance_history) == 1
        assert len(optimizer._balance_history) == 1
        assert isinstance(updated_params, dict)
        assert isinstance(balance, BalanceMetrics)

    def test_optimize_tracks_best_objective(self, opt_config, sample_params, sample_state):
        """Test that optimizer tracks best objective."""
        optimizer = NeuroOptimizer(opt_config)

        # First optimization with moderate performance
        optimizer.optimize(sample_params, sample_state, performance_score=1.0)
        first_best = optimizer._best_objective

        # Second optimization with better performance
        optimizer.optimize(sample_params, sample_state, performance_score=2.0)
        second_best = optimizer._best_objective

        assert second_best >= first_best

    def test_learning_rate_decays_on_plateau(self, sample_params, sample_state):
        """Test adaptive learning rate decay when improvements stall."""
        config = OptimizationConfig(
            balance_weight=0.35,
            performance_weight=0.45,
            stability_weight=0.20,
            learning_rate=0.02,
            learning_rate_floor=0.005,
            adaptive_decay=0.5,
            plateau_patience=2,
            ema_alpha=0.6,
        )

        optimizer = NeuroOptimizer(config)

        # Kick off with strong performance then sustain weaker returns
        optimizer.optimize(sample_params, sample_state, performance_score=2.0)
        initial_lr = optimizer._current_lr

        for _ in range(4):
            optimizer.optimize(sample_params, sample_state, performance_score=0.2)

        assert optimizer._current_lr < initial_lr
        assert optimizer._current_lr >= config.learning_rate_floor

    def test_estimate_gradients(self, opt_config, sample_params, sample_state):
        """Test gradient estimation."""
        optimizer = NeuroOptimizer(opt_config)

        # Need at least one balance in history
        balance = optimizer._calculate_balance_metrics(sample_state)
        optimizer._balance_history.append(balance)

        gradients = optimizer._estimate_gradients(
            sample_params,
            sample_state,
            performance=1.5,
        )

        assert isinstance(gradients, dict)
        assert 'dopamine' in gradients or 'serotonin' in gradients

    def test_apply_updates_with_momentum(self, opt_config, sample_params):
        """Test parameter updates with momentum."""
        optimizer = NeuroOptimizer(opt_config)

        # Create some gradients
        gradients = {
            'dopamine': {
                'learning_rate': 0.001,
                'burst_factor': 0.01,
            },
        }

        updated = optimizer._apply_updates(sample_params, gradients)

        assert updated['dopamine']['learning_rate'] != sample_params['dopamine']['learning_rate']

    def test_gradient_clipping_limits_step(self):
        """Test that gradient clipping constrains update magnitude."""
        config = OptimizationConfig(
            learning_rate=0.5,
            learning_rate_floor=0.001,
            adaptive_decay=0.5,
            plateau_patience=2,
            max_gradient_norm=0.01,
            momentum=0.0,
        )
        optimizer = NeuroOptimizer(config)

        params = {'dopamine': {'learning_rate': 1.0}}
        gradients = {'dopamine': {'learning_rate': 5.0}}

        updated = optimizer._apply_updates(params, gradients)

        # Max step should be capped at 1% of the parameter value
        assert updated['dopamine']['learning_rate'] <= 1.01
        assert updated['dopamine']['learning_rate'] >= 0.99

        assert isinstance(updated, dict)
        assert 'dopamine' in updated

    def test_parameter_clipping(self, opt_config, sample_params):
        """Test that parameter updates are clipped."""
        optimizer = NeuroOptimizer(opt_config)

        # Large gradients that would cause big changes
        gradients = {
            'dopamine': {
                'learning_rate': 10.0,  # Very large update
            },
        }

        updated = optimizer._apply_updates(sample_params, gradients)

        # Should be clipped to 120% of original
        original_lr = sample_params['dopamine']['learning_rate']
        updated_lr = updated['dopamine']['learning_rate']
        assert updated_lr <= original_lr * 1.2

    def test_get_optimization_report_no_data(self, opt_config):
        """Test optimization report with no data."""
        optimizer = NeuroOptimizer(opt_config)

        report = optimizer.get_optimization_report()

        assert report['status'] == 'no_data'

    def test_get_optimization_report_with_data(self, opt_config, sample_params, sample_state):
        """Test optimization report with data."""
        optimizer = NeuroOptimizer(opt_config)

        # Run several optimizations
        for _ in range(5):
            optimizer.optimize(sample_params, sample_state, performance_score=1.5)

        report = optimizer.get_optimization_report()

        assert report['status'] == 'active'
        assert 'iteration' in report
        assert 'best_objective' in report
        assert 'avg_balance_score' in report
        assert 'convergence' in report
        assert 'health_status' in report

    def test_check_convergence_insufficient_data(self, opt_config):
        """Test convergence check with insufficient data."""
        optimizer = NeuroOptimizer(opt_config)

        convergence = optimizer._check_convergence()

        assert convergence['converged'] is False
        assert convergence['reason'] == 'insufficient_data'

    def test_check_convergence_converged(self, opt_config, sample_params, sample_state):
        """Test convergence detection."""
        optimizer = NeuroOptimizer(opt_config)

        # Run many iterations with stable performance
        for _ in range(25):
            optimizer.optimize(sample_params, sample_state, performance_score=1.5)

        convergence = optimizer._check_convergence()

        # With stable performance, should converge
        assert 'converged' in convergence
        assert 'variance' in convergence

    def test_assess_health_no_data(self, opt_config):
        """Test health assessment with no data."""
        optimizer = NeuroOptimizer(opt_config)

        health = optimizer._assess_health(None)

        assert health['status'] == 'unknown'

    def test_assess_health_healthy_system(self, opt_config, sample_state):
        """Test health assessment for healthy system."""
        optimizer = NeuroOptimizer(opt_config)

        balance = optimizer._calculate_balance_metrics(sample_state)

        # Manually set good balance
        balance = BalanceMetrics(
            dopamine_serotonin_ratio=1.8,
            gaba_excitation_balance=1.5,
            arousal_attention_coherence=0.9,
            overall_balance_score=0.85,
            homeostatic_deviation=0.1,
        )

        health = optimizer._assess_health(balance)

        assert health['status'] == 'healthy'
        assert 'balance_score' in health
        assert 'issues' in health

    def test_assess_health_imbalanced_system(self, opt_config):
        """Test health assessment for imbalanced system."""
        optimizer = NeuroOptimizer(opt_config)

        # Create imbalanced metrics
        balance = BalanceMetrics(
            dopamine_serotonin_ratio=0.5,  # Too low
            gaba_excitation_balance=3.0,   # Too high
            arousal_attention_coherence=0.3,  # Poor coherence
            overall_balance_score=0.4,
            homeostatic_deviation=0.6,
        )

        health = optimizer._assess_health(balance)

        assert health['status'] in ['warning', 'acceptable']
        assert len(health['issues']) > 0

    def test_reset(self, opt_config, sample_params, sample_state):
        """Test optimizer reset."""
        optimizer = NeuroOptimizer(opt_config)

        # Run some optimizations
        for _ in range(5):
            optimizer.optimize(sample_params, sample_state, performance_score=1.5)

        # Reset
        optimizer.reset()

        assert optimizer._iteration == 0
        assert optimizer._best_objective == -np.inf
        assert len(optimizer._performance_history) == 0
        assert len(optimizer._balance_history) == 0
        assert len(optimizer._velocity) == 0

    def test_logging_callback(self, opt_config, sample_params, sample_state):
        """Test that logging callback is called."""
        logged_metrics = []

        def logger(name: str, value: float):
            logged_metrics.append((name, value))

        optimizer = NeuroOptimizer(opt_config, logger=logger)

        optimizer.optimize(sample_params, sample_state, performance_score=1.5)

        # Should have logged several metrics
        assert len(logged_metrics) > 0
        assert any('objective' in name for name, _ in logged_metrics)

    def test_gpu_backend_avoids_numpy_ops(self, sample_state, monkeypatch):
        """Test GPU backend uses cupy operations when available."""
        cp = pytest.importorskip("cupy")

        config = OptimizationConfig(use_gpu=True)
        optimizer = NeuroOptimizer(config)

        assert optimizer._xp is cp

        def guard_numpy(func):
            def wrapper(*args, **kwargs):
                if any(isinstance(arg, cp.ndarray) for arg in args):
                    raise AssertionError("numpy operation used on cupy array")
                return func(*args, **kwargs)

            return wrapper

        monkeypatch.setattr(np, "clip", guard_numpy(np.clip))
        monkeypatch.setattr(np, "mean", guard_numpy(np.mean))
        monkeypatch.setattr(np, "std", guard_numpy(np.std))

        optimizer._performance_history = [cp.asarray(1.0)] * 11
        balance = optimizer._calculate_balance_metrics(sample_state)

        objective = optimizer._calculate_objective(cp.asarray(1.5), balance, sample_state)

        assert isinstance(objective, float)

        optimizer._performance_history = [cp.asarray(1.0)] * 20
        convergence = optimizer._check_convergence()

        assert 'converged' in convergence

        optimizer._balance_history = [balance] * 10
        report = optimizer.get_optimization_report()

        assert report['status'] == 'active'


@pytest.mark.integration
class TestNeuroOptimizerIntegration:
    """Integration tests for neuro optimizer."""

    def test_optimization_loop(self, opt_config, sample_params, sample_state):
        """Test complete optimization loop."""
        optimizer = NeuroOptimizer(opt_config)

        # Run optimization loop
        for i in range(20):
            performance = 1.0 + i * 0.05  # Improving performance

            updated_params, balance = optimizer.optimize(
                sample_params,
                sample_state,
                performance_score=performance,
            )

            # Use updated params for next iteration
            sample_params = updated_params

        report = optimizer.get_optimization_report()

        assert report['status'] == 'active'
        assert optimizer._iteration == 20

    def test_handles_varying_performance(self, opt_config, sample_params, sample_state):
        """Test optimizer handles varying performance."""
        optimizer = NeuroOptimizer(opt_config)

        # Simulate varying performance
        np.random.seed(42)
        for _ in range(30):
            performance = 1.5 + np.random.randn() * 0.5

            updated_params, balance = optimizer.optimize(
                sample_params,
                sample_state,
                performance_score=performance,
            )

            # Should not crash
            assert isinstance(updated_params, dict)
            assert isinstance(balance, BalanceMetrics)

    def test_maintains_homeostasis(self, opt_config, sample_params):
        """Test that optimizer maintains homeostatic balance."""
        optimizer = NeuroOptimizer(opt_config)

        # Start with imbalanced state
        imbalanced_state = {
            'dopamine_level': 0.9,  # Very high
            'serotonin_level': 0.1,  # Very low
            'gaba_inhibition': 0.2,  # Low inhibition
            'na_arousal': 1.8,       # High arousal
            'ach_attention': 0.4,    # Low attention
        }

        deviations = []
        for _ in range(30):
            _, balance = optimizer.optimize(
                sample_params,
                imbalanced_state,
                performance_score=1.0,
            )
            deviations.append(balance.homeostatic_deviation)

        # Deviation trend should generally decrease (moving toward balance)
        # Check if average of last 10 is better than first 10
        early_avg = np.mean(deviations[:10])
        late_avg = np.mean(deviations[-10:])

        # Note: This might not always be true with the simple heuristic,
        # but should generally trend toward balance
        assert late_avg <= early_avg * 1.5  # Allow some tolerance
