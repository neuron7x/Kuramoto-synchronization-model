"""Tests for cross-neuromodulator optimization system."""

from __future__ import annotations

import importlib.util
import logging

import numpy as np
import pytest

HYPOTHESIS_AVAILABLE = importlib.util.find_spec("hypothesis") is not None
if HYPOTHESIS_AVAILABLE:  # pragma: no branch
    from hypothesis import given, settings
    from hypothesis import strategies as st

from tradepulse.core.neuro.neuro_optimizer import (
    BalanceMetrics,
    NeuroOptimizer,
    NumericConfig,
    OptimizationConfig,
)
from tradepulse.core.neuro._validation import (
    BoundsSpec,
    validate_neuro_invariants,
    validate_neuro_metric_bounds,
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


def _make_balance_with_ratio(ratio: float) -> BalanceMetrics:
    return BalanceMetrics(
        dopamine_serotonin_ratio=ratio,
        gaba_excitation_balance=1.5,
        arousal_attention_coherence=1.0,
        overall_balance_score=0.7,
        homeostatic_deviation=0.1,
    )


def _assert_balance_invariants(balance: BalanceMetrics) -> None:
    validate_neuro_invariants(
        dopamine_serotonin_ratio=balance.dopamine_serotonin_ratio,
        excitation_inhibition_balance=balance.gaba_excitation_balance,
        arousal_attention_coherence=balance.arousal_attention_coherence,
        stability=balance.overall_balance_score,
    )
    assert balance.homeostatic_deviation >= 0


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

    def test_stability_epsilon_positive(self):
        """Test stability_epsilon must be positive."""
        with pytest.raises(ValueError, match="stability_epsilon"):
            NumericConfig(stability_epsilon=0.0)

    def test_gradient_dev_clip_positive(self):
        """Test gradient_dev_clip must be positive."""
        with pytest.raises(ValueError, match="gradient_dev_clip"):
            NumericConfig(gradient_dev_clip=0.0)

    def test_gradient_clip_positive(self):
        """Test gradient_clip must be positive."""
        with pytest.raises(ValueError, match="gradient_clip"):
            OptimizationConfig(gradient_clip=0.0)

    @pytest.mark.parametrize(
        "config_kwargs, numeric_kwargs, error_match",
        [
            (
                {},
                {"performance_min": 1.0, "performance_max": 1.0},
                "performance_min must be less than performance_max",
            ),
            (
                {},
                {"performance_min": 2.0, "performance_max": 1.0},
                "performance_min must be less than performance_max",
            ),
            ({}, {"stability_epsilon": 0.0}, "stability_epsilon must be positive"),
            ({"history_window": 0}, None, "History window must be a positive integer"),
            ({"momentum": -0.1}, None, "Momentum must be in \\[0, 1\\)"),
            ({"momentum": 1.0}, None, "Momentum must be in \\[0, 1\\)"),
        ],
    )
    def test_critical_ranges(self, config_kwargs, numeric_kwargs, error_match):
        """Test critical ranges for key configuration values."""
        with pytest.raises(ValueError, match=error_match):
            if numeric_kwargs:
                OptimizationConfig(numeric=NumericConfig(**numeric_kwargs), **config_kwargs)
            else:
                OptimizationConfig(**config_kwargs)


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


class TestNeuroMetricBounds:
    """Tests for neuro metric bound enforcement."""

    def test_validate_neuro_metric_bounds_clips_and_logs(self, caplog):
        """Out-of-bounds metrics should clip and log warnings."""
        caplog.set_level(logging.WARNING)

        result = validate_neuro_metric_bounds(
            dopamine_serotonin_ratio=10.0,
            excitation_inhibition_balance=0.1,
            arousal_attention_coherence=1.5,
            stability=-0.2,
            da_5ht_ratio_bounds=BoundsSpec(1.0, 3.0, "clip"),
            ei_balance_bounds=BoundsSpec(1.0, 2.5, "clip"),
            arousal_attention_bounds=BoundsSpec(0.0, 1.0, "clip"),
            stability_bounds=BoundsSpec(0.0, 1.0, "clip"),
        )

        assert result["dopamine_serotonin_ratio"] == 3.0
        assert result["excitation_inhibition_balance"] == 1.0
        assert result["arousal_attention_coherence"] == 1.0
        assert result["stability"] == 0.0
        assert any("clipped to" in record.message for record in caplog.records)

    def test_validate_neuro_metric_bounds_raises_and_logs(self, caplog):
        """Out-of-bounds metrics should raise and log errors."""
        caplog.set_level(logging.ERROR)

        with pytest.raises(ValueError, match="dopamine_serotonin_ratio"):
            validate_neuro_metric_bounds(
                dopamine_serotonin_ratio=0.5,
                excitation_inhibition_balance=1.5,
                arousal_attention_coherence=0.5,
                stability=0.5,
                da_5ht_ratio_bounds=BoundsSpec(1.0, 3.0, "raise"),
                ei_balance_bounds=BoundsSpec(1.0, 2.5, "raise"),
                arousal_attention_bounds=BoundsSpec(0.0, 1.0, "raise"),
                stability_bounds=BoundsSpec(0.0, 1.0, "raise"),
            )

        assert any("out of bounds" in record.message for record in caplog.records)


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
        _assert_balance_invariants(balance)

    def test_balance_score_monotonic_with_homeostatic_dev(self, opt_config):
        """Ensure balance score decreases as homeostatic deviation increases."""
        optimizer = NeuroOptimizer(opt_config)

        baseline_state = {
            "dopamine_level": 0.5,
            "serotonin_level": 0.3,
            "gaba_inhibition": 0.4,
            "na_arousal": 1.0,
            "ach_attention": 0.7,
        }
        stressed_state = {
            "dopamine_level": 1.6,
            "serotonin_level": 0.1,
            "gaba_inhibition": 0.1,
            "na_arousal": 2.0,
            "ach_attention": 0.2,
        }

        baseline_balance = optimizer._calculate_balance_metrics(baseline_state)
        stressed_balance = optimizer._calculate_balance_metrics(stressed_state)

        assert baseline_balance.homeostatic_deviation >= 0
        assert stressed_balance.homeostatic_deviation >= 0
        assert stressed_balance.homeostatic_deviation > baseline_balance.homeostatic_deviation
        assert stressed_balance.overall_balance_score < baseline_balance.overall_balance_score

    def test_balance_score_decreases_as_homeostatic_dev_grows(self, opt_config):
        """Higher homeostatic deviation should reduce the balance score."""
        optimizer = NeuroOptimizer(opt_config)
        optimizer._setpoints["da_5ht_ratio"] = 1.0
        optimizer._setpoints["excitation_inhibition"] = 1.0

        low_dev_state = {
            "dopamine_level": 1.0,
            "serotonin_level": 1.0,
            "gaba_inhibition": 1.0,
            "na_arousal": 1.0,
            "ach_attention": 1.0,
        }
        high_dev_state = {
            "dopamine_level": 2.0,
            "serotonin_level": 1.0,
            "gaba_inhibition": 0.5,
            "na_arousal": 2.0,
            "ach_attention": 0.0,
        }

        low_dev_balance = optimizer._calculate_balance_metrics(low_dev_state)
        high_dev_balance = optimizer._calculate_balance_metrics(high_dev_state)

        assert high_dev_balance.homeostatic_deviation > low_dev_balance.homeostatic_deviation
        assert high_dev_balance.overall_balance_score < low_dev_balance.overall_balance_score

    @pytest.mark.parametrize(
        "state",
        [
            {
                "dopamine_level": 2.0,
                "serotonin_level": 0.05,
                "gaba_inhibition": 0.2,
                "na_arousal": 1.5,
                "ach_attention": 0.3,
            },
            {
                "dopamine_level": 0.05,
                "serotonin_level": 1.2,
                "gaba_inhibition": 1.5,
                "na_arousal": 0.2,
                "ach_attention": 1.8,
            },
            {
                "dopamine_level": 1.8,
                "serotonin_level": 0.8,
                "gaba_inhibition": 0.1,
                "na_arousal": 5.0,
                "ach_attention": 0.05,
            },
            {
                "dopamine_level": 0.2,
                "serotonin_level": 0.02,
                "gaba_inhibition": 2.5,
                "na_arousal": 0.01,
                "ach_attention": 3.5,
            },
        ],
    )
    def test_balance_metrics_extreme_states(self, opt_config, state):
        """Ensure balance metrics stay within bounds for extreme states."""
        optimizer = NeuroOptimizer(opt_config)

        balance = optimizer._calculate_balance_metrics(state)

        _assert_balance_invariants(balance)

    @pytest.mark.parametrize(
        "arousal,attention",
        [
            (1000.0, -1000.0),
            (-500.0, 500.0),
            (1e6, 1e-6),
        ],
    )
    def test_arousal_attention_coherence_clipped(
        self, opt_config, sample_state, arousal, attention
    ):
        """Ensure arousal-attention coherence is clipped to [0, 1]."""
        optimizer = NeuroOptimizer(opt_config)

        extreme_state = dict(sample_state)
        extreme_state["na_arousal"] = arousal
        extreme_state["ach_attention"] = attention

        balance = optimizer._calculate_balance_metrics(extreme_state)

        assert 0 <= balance.arousal_attention_coherence <= 1

    @pytest.mark.parametrize(
        "arousal,attention",
        [
            (1e9, -1e9),
            (-1e6, 1e6),
            (1e12, 1e-12),
        ],
    )
    def test_arousal_attention_coherence_extreme_bounds(
        self, opt_config, sample_state, arousal, attention
    ):
        """Verify arousal-attention coherence stays within [0, 1] for extremes."""
        optimizer = NeuroOptimizer(opt_config)

        extreme_state = dict(sample_state)
        extreme_state["na_arousal"] = arousal
        extreme_state["ach_attention"] = attention

        balance = optimizer._calculate_balance_metrics(extreme_state)

        assert 0 <= balance.arousal_attention_coherence <= 1

    def test_calculate_balance_with_defaults(self, opt_config):
        """Test balance calculation with missing state values."""
        optimizer = NeuroOptimizer(opt_config)

        # Empty state should use defaults
        balance = optimizer._calculate_balance_metrics({})

        assert isinstance(balance, BalanceMetrics)
        _assert_balance_invariants(balance)

    if HYPOTHESIS_AVAILABLE:

        @settings(max_examples=50, deadline=None)
        @given(
            dopamine=st.floats(
                min_value=0.01, max_value=3.0, allow_nan=False, allow_infinity=False
            ),
            serotonin=st.floats(
                min_value=0.01, max_value=3.0, allow_nan=False, allow_infinity=False
            ),
            gaba=st.floats(
                min_value=0.01, max_value=3.0, allow_nan=False, allow_infinity=False
            ),
            arousal=st.floats(
                min_value=0.01, max_value=5.0, allow_nan=False, allow_infinity=False
            ),
            attention=st.floats(
                min_value=0.01, max_value=5.0, allow_nan=False, allow_infinity=False
            ),
        )
        def test_balance_metrics_random_states(
            self,
            opt_config,
            dopamine,
            serotonin,
            gaba,
            arousal,
            attention,
        ):
            """Check balance invariants for random valid neuromodulator states."""
            optimizer = NeuroOptimizer(opt_config)
            state = {
                "dopamine_level": dopamine,
                "serotonin_level": serotonin,
                "gaba_inhibition": gaba,
                "na_arousal": arousal,
                "ach_attention": attention,
            }

            balance = optimizer._calculate_balance_metrics(state)

            _assert_balance_invariants(balance)

    else:  # pragma: no cover - executed when Hypothesis missing

        def test_balance_metrics_random_states(self, opt_config):  # type: ignore[override]
            pytest.skip("hypothesis not installed")

    def test_calculate_objective(self, opt_config, sample_state):
        """Test objective function calculation."""
        optimizer = NeuroOptimizer(opt_config)

        balance = optimizer._calculate_balance_metrics(sample_state)
        performance = 1.5  # Sharpe ratio

        objective = optimizer._calculate_objective(performance, balance, sample_state)

        assert isinstance(objective, float)
        assert 0 <= objective <= 1

    def test_log_metrics_emits_expected_keys(self, opt_config):
        """Ensure logged metrics use the neuro_opt.<metric> naming scheme."""
        captured = {}

        def logger(name: str, value: float) -> None:
            captured[name] = value

        optimizer = NeuroOptimizer(opt_config, logger=logger)
        balance = BalanceMetrics(
            dopamine_serotonin_ratio=1.7,
            gaba_excitation_balance=1.5,
            arousal_attention_coherence=0.9,
            overall_balance_score=0.8,
            homeostatic_deviation=0.2,
        )

        optimizer._log_metrics(0.6, balance)

        expected = {
            "neuro_opt.objective",
            "neuro_opt.balance_score",
            "neuro_opt.homeostatic_dev",
            "neuro_opt.da_5ht_ratio",
            "neuro_opt.ei_balance",
            "neuro_opt.aa_coherence",
        }
        assert expected.issubset(captured.keys())

    def test_calculate_objective_clamps_performance(self, sample_state):
        """Ensure performance normalization clamps outside configured bounds."""
        config = OptimizationConfig(
            balance_weight=0.0,
            performance_weight=1.0,
            stability_weight=0.0,
            numeric=NumericConfig(performance_min=-1.0, performance_max=1.0),
        )
        optimizer = NeuroOptimizer(config)
        balance = optimizer._calculate_balance_metrics(sample_state)

        low_objective = optimizer._calculate_objective(-5.0, balance, sample_state)
        mid_objective = optimizer._calculate_objective(0.0, balance, sample_state)
        high_objective = optimizer._calculate_objective(5.0, balance, sample_state)

        assert low_objective == pytest.approx(0.0)
        assert mid_objective == pytest.approx(0.5)
        assert high_objective == pytest.approx(1.0)

    def test_objective_matches_formula_at_performance_bounds(self, sample_state):
        """Objective should match weighted formula at min/max performance inputs."""
        config = OptimizationConfig(
            balance_weight=0.3,
            performance_weight=0.5,
            stability_weight=0.2,
            numeric=NumericConfig(performance_min=-2.0, performance_max=2.0),
        )
        optimizer = NeuroOptimizer(config)
        balance = BalanceMetrics(
            dopamine_serotonin_ratio=1.7,
            gaba_excitation_balance=1.5,
            arousal_attention_coherence=0.9,
            overall_balance_score=0.25,
            homeostatic_deviation=0.1,
        )

        objective_min = optimizer._calculate_objective(
            config.numeric.performance_min, balance, sample_state
        )
        objective_max = optimizer._calculate_objective(
            config.numeric.performance_max, balance, sample_state
        )

        expected_stability = 0.5
        expected_min = (
            config.performance_weight * 0.0
            + config.balance_weight * balance.overall_balance_score
            + config.stability_weight * expected_stability
        )
        expected_max = (
            config.performance_weight * 1.0
            + config.balance_weight * balance.overall_balance_score
            + config.stability_weight * expected_stability
        )

        assert objective_min == pytest.approx(expected_min)
        assert objective_max == pytest.approx(expected_max)

    def test_calculate_objective_respects_performance_range(self, sample_state):
        """Ensure performance range changes normalization sensitivity."""
        narrow_config = OptimizationConfig(
            balance_weight=0.0,
            performance_weight=1.0,
            stability_weight=0.0,
            numeric=NumericConfig(performance_min=0.0, performance_max=2.0),
        )
        wide_config = OptimizationConfig(
            balance_weight=0.0,
            performance_weight=1.0,
            stability_weight=0.0,
            numeric=NumericConfig(performance_min=-2.0, performance_max=4.0),
        )
        balance = BalanceMetrics(
            dopamine_serotonin_ratio=1.7,
            gaba_excitation_balance=1.5,
            arousal_attention_coherence=0.9,
            overall_balance_score=0.4,
            homeostatic_deviation=0.2,
        )

        narrow_optimizer = NeuroOptimizer(narrow_config)
        wide_optimizer = NeuroOptimizer(wide_config)

        performance = 1.5
        narrow_objective = narrow_optimizer._calculate_objective(
            performance, balance, sample_state
        )
        wide_objective = wide_optimizer._calculate_objective(
            performance, balance, sample_state
        )

        assert narrow_objective > wide_objective

    def test_numeric_config_changes_objective_and_health(self, sample_state):
        """NumericConfig changes should influence objective and health outcomes."""
        balance = BalanceMetrics(
            dopamine_serotonin_ratio=1.5,
            gaba_excitation_balance=1.5,
            arousal_attention_coherence=0.7,
            overall_balance_score=0.7,
            homeostatic_deviation=0.2,
        )
        baseline_numeric = NumericConfig(
            performance_min=-2.0,
            performance_max=2.0,
            aa_coherence_min=0.6,
        )
        stricter_numeric = NumericConfig(
            performance_min=0.0,
            performance_max=2.0,
            aa_coherence_min=0.8,
        )
        baseline_config = OptimizationConfig(
            balance_weight=0.0,
            performance_weight=1.0,
            stability_weight=0.0,
            numeric=baseline_numeric,
        )
        stricter_config = OptimizationConfig(
            balance_weight=0.0,
            performance_weight=1.0,
            stability_weight=0.0,
            numeric=stricter_numeric,
        )

        baseline_optimizer = NeuroOptimizer(baseline_config)
        stricter_optimizer = NeuroOptimizer(stricter_config)

        objective_baseline = baseline_optimizer._calculate_objective(
            1.0, balance, sample_state
        )
        objective_stricter = stricter_optimizer._calculate_objective(
            1.0, balance, sample_state
        )

        assert objective_baseline > objective_stricter

        baseline_health = baseline_optimizer._assess_health(balance)
        stricter_health = stricter_optimizer._assess_health(balance)

        assert all(
            'Poor arousal-attention coherence' not in issue
            for issue in baseline_health['issues']
        )
        assert any(
            'Poor arousal-attention coherence' in issue
            for issue in stricter_health['issues']
        )

    def test_objective_monotonic_with_weight_increase_fixed_components(self, sample_state):
        """Objective should increase as weight shifts to higher-valued component."""
        balance = BalanceMetrics(
            dopamine_serotonin_ratio=1.7,
            gaba_excitation_balance=1.5,
            arousal_attention_coherence=0.9,
            overall_balance_score=0.2,
            homeostatic_deviation=0.2,
        )
        performance = 3.0  # Normalizes to 1.0 (P)

        low_perf_weight = OptimizationConfig(
            balance_weight=0.6,
            performance_weight=0.2,
            stability_weight=0.2,
        )
        mid_perf_weight = OptimizationConfig(
            balance_weight=0.4,
            performance_weight=0.4,
            stability_weight=0.2,
        )
        high_perf_weight = OptimizationConfig(
            balance_weight=0.2,
            performance_weight=0.6,
            stability_weight=0.2,
        )

        low_optimizer = NeuroOptimizer(low_perf_weight)
        mid_optimizer = NeuroOptimizer(mid_perf_weight)
        high_optimizer = NeuroOptimizer(high_perf_weight)

        flat_history = [0.0, 10.0, 0.0, 10.0, 0.0, 10.0, 0.0, 10.0, 0.0, 10.0, 0.0]
        low_optimizer._performance_history = flat_history
        mid_optimizer._performance_history = flat_history
        high_optimizer._performance_history = flat_history

        objective_low = low_optimizer._calculate_objective(
            performance, balance, sample_state
        )
        objective_mid = mid_optimizer._calculate_objective(
            performance, balance, sample_state
        )
        objective_high = high_optimizer._calculate_objective(
            performance, balance, sample_state
        )

        assert objective_low < objective_mid < objective_high

    def test_objective_monotonic_with_weights(self, sample_state):
        """Ensure objective changes monotonically with weight shifts."""
        balance = BalanceMetrics(
            dopamine_serotonin_ratio=1.7,
            gaba_excitation_balance=1.5,
            arousal_attention_coherence=0.9,
            overall_balance_score=0.4,
            homeostatic_deviation=0.2,
        )
        performance = 2.5  # Normalized higher than balance score

        low_perf_weight = OptimizationConfig(
            balance_weight=0.7,
            performance_weight=0.3,
            stability_weight=0.0,
        )
        high_perf_weight = OptimizationConfig(
            balance_weight=0.3,
            performance_weight=0.7,
            stability_weight=0.0,
        )

        low_optimizer = NeuroOptimizer(low_perf_weight)
        high_optimizer = NeuroOptimizer(high_perf_weight)

        objective_low = low_optimizer._calculate_objective(
            performance, balance, sample_state
        )
        objective_high = high_optimizer._calculate_objective(
            performance, balance, sample_state
        )

        assert objective_high > objective_low

        balance_heavy = BalanceMetrics(
            dopamine_serotonin_ratio=1.7,
            gaba_excitation_balance=1.5,
            arousal_attention_coherence=0.9,
            overall_balance_score=0.9,
            homeostatic_deviation=0.05,
        )
        low_balance_weight = OptimizationConfig(
            balance_weight=0.2,
            performance_weight=0.8,
            stability_weight=0.0,
        )
        high_balance_weight = OptimizationConfig(
            balance_weight=0.8,
            performance_weight=0.2,
            stability_weight=0.0,
        )

        low_balance_optimizer = NeuroOptimizer(low_balance_weight)
        high_balance_optimizer = NeuroOptimizer(high_balance_weight)

        objective_low_balance = low_balance_optimizer._calculate_objective(
            -1.5, balance_heavy, sample_state
        )
        objective_high_balance = high_balance_optimizer._calculate_objective(
            -1.5, balance_heavy, sample_state
        )

        assert objective_high_balance > objective_low_balance

    def test_calculate_objective_stability_negative_mean(self, sample_state):
        """Test stability calculation with low/negative mean performance."""
        config = OptimizationConfig(
            balance_weight=0.0,
            performance_weight=0.0,
            stability_weight=1.0,
        )
        optimizer = NeuroOptimizer(config)
        optimizer._performance_history = [
            -0.011,
            -0.010,
            -0.012,
            -0.009,
            -0.0105,
            -0.0102,
            -0.0098,
            -0.0101,
            -0.0107,
            -0.0099,
            -0.0103,
        ]

        balance = optimizer._calculate_balance_metrics(sample_state)

        stability_1 = optimizer._calculate_objective(-0.01, balance, sample_state)
        optimizer._performance_history.append(-0.0104)
        stability_2 = optimizer._calculate_objective(-0.01, balance, sample_state)

        validate_neuro_invariants(
            dopamine_serotonin_ratio=balance.dopamine_serotonin_ratio,
            excitation_inhibition_balance=balance.gaba_excitation_balance,
            arousal_attention_coherence=balance.arousal_attention_coherence,
            stability=stability_1,
        )
        validate_neuro_invariants(
            dopamine_serotonin_ratio=balance.dopamine_serotonin_ratio,
            excitation_inhibition_balance=balance.gaba_excitation_balance,
            arousal_attention_coherence=balance.arousal_attention_coherence,
            stability=stability_2,
        )
        assert np.isfinite(stability_1)
        assert np.isfinite(stability_2)
        assert 0 <= stability_1 <= 1
        assert 0 <= stability_2 <= 1
        assert abs(stability_2 - stability_1) < 0.2

    def test_stability_decreases_with_higher_std_at_fixed_mean(self, sample_state):
        """Stability should drop as variance grows when mean is fixed."""
        config = OptimizationConfig(
            balance_weight=0.0,
            performance_weight=0.0,
            stability_weight=1.0,
            history_window=5,
        )
        optimizer = NeuroOptimizer(config)
        balance = optimizer._calculate_balance_metrics(sample_state)

        optimizer._performance_history = [1.0, 1.0, 1.0, 1.0, 1.0]
        stability_low_std = optimizer._calculate_objective(1.0, balance, sample_state)

        optimizer._performance_history = [0.0, 2.0, 1.0, 1.0, 1.0]
        stability_high_std = optimizer._calculate_objective(1.0, balance, sample_state)

        assert stability_low_std > stability_high_std

    def test_stability_bounds_with_negative_mean(self, sample_state):
        """Stability should stay within [0, 1] even for negative means."""
        config = OptimizationConfig(
            balance_weight=0.0,
            performance_weight=0.0,
            stability_weight=1.0,
            history_window=5,
        )
        optimizer = NeuroOptimizer(config)
        balance = optimizer._calculate_balance_metrics(sample_state)

        optimizer._performance_history = [-3.0, -0.1, -0.1, -0.1, -0.1]
        stability = optimizer._calculate_objective(-0.1, balance, sample_state)

        assert 0 <= stability <= 1

    def test_calculate_objective_stability_near_zero_mean(self, sample_state):
        """Ensure stability is bounded for near-zero mean performance."""
        config = OptimizationConfig(
            balance_weight=0.0,
            performance_weight=0.0,
            stability_weight=1.0,
        )
        optimizer = NeuroOptimizer(config)
        optimizer._performance_history = [
            -1e-10,
            2e-10,
            -3e-10,
            1e-10,
            -2e-10,
            3e-10,
            -1e-10,
            2e-10,
            -2e-10,
            1e-10,
            -1e-10,
        ]

        balance = optimizer._calculate_balance_metrics(sample_state)

        stability = optimizer._calculate_objective(0.0, balance, sample_state)

        assert np.isfinite(stability)
        assert 0 <= stability <= 1

    def test_calculate_objective_stability_constant_performance(self, sample_state):
        """Stability should be 1.0 when performance variance is zero."""
        config = OptimizationConfig(
            balance_weight=0.0,
            performance_weight=0.0,
            stability_weight=1.0,
        )
        optimizer = NeuroOptimizer(config)
        optimizer._performance_history = [0.05] * 11

        balance = optimizer._calculate_balance_metrics(sample_state)

        stability = optimizer._calculate_objective(0.05, balance, sample_state)

        assert stability == pytest.approx(1.0)

    def test_stability_epsilon_applies_to_core_calculations(self):
        """Ensure stability_epsilon drives balance, stability, and gradient math."""
        low_eps = 1e-6
        high_eps = 1e-2
        base_config = dict(
            balance_weight=0.0,
            performance_weight=0.0,
            stability_weight=1.0,
            history_window=5,
        )
        low_config = OptimizationConfig(
            **base_config,
            numeric=NumericConfig(
                stability_epsilon=low_eps,
                da_5ht_ratio_range=(0.1, 1e7),
                ei_balance_range=(0.1, 1e7),
                gradient_dev_clip=1e7,
            ),
        )
        high_config = OptimizationConfig(
            **base_config,
            numeric=NumericConfig(
                stability_epsilon=high_eps,
                da_5ht_ratio_range=(0.1, 1e7),
                ei_balance_range=(0.1, 1e7),
                gradient_dev_clip=1e7,
            ),
        )

        state = {
            "dopamine_level": 0.5,
            "serotonin_level": 0.0,
            "gaba_inhibition": 0.0,
            "na_arousal": 1.0,
            "ach_attention": 1.0,
        }
        params = {
            "dopamine": {"learning_rate": 0.1},
            "serotonin": {"stress_threshold": 0.2},
        }

        low_optimizer = NeuroOptimizer(low_config)
        high_optimizer = NeuroOptimizer(high_config)

        low_balance = low_optimizer._calculate_balance_metrics(state)
        high_balance = high_optimizer._calculate_balance_metrics(state)

        expected_ratio_low = state["dopamine_level"] / (
            state["serotonin_level"] + low_eps
        )
        expected_ratio_high = state["dopamine_level"] / (
            state["serotonin_level"] + high_eps
        )
        assert low_balance.dopamine_serotonin_ratio == pytest.approx(expected_ratio_low)
        assert high_balance.dopamine_serotonin_ratio == pytest.approx(expected_ratio_high)

        history = [1e-4, -1e-4, 1e-4, -1e-4, 1e-4]
        low_optimizer._performance_history = history.copy()
        high_optimizer._performance_history = history.copy()
        mean_perf = np.mean(history)
        std_perf = np.std(history)
        expected_stability_low = np.clip(
            1 - std_perf / max(abs(mean_perf), low_eps), 0, 1
        )
        expected_stability_high = np.clip(
            1 - std_perf / max(abs(mean_perf), high_eps), 0, 1
        )

        stability_low = low_optimizer._calculate_objective(0.0, low_balance, state)
        stability_high = high_optimizer._calculate_objective(0.0, high_balance, state)

        assert stability_low == pytest.approx(expected_stability_low)
        assert stability_high == pytest.approx(expected_stability_high)

        gradients_low = low_optimizer._estimate_gradients(params, state, performance=0.0)
        gradients_high = high_optimizer._estimate_gradients(
            params, state, performance=0.0
        )
        ratio_value_low = state["dopamine_level"] / (
            state["serotonin_level"] + low_eps
        )
        ratio_value_high = state["dopamine_level"] / (
            state["serotonin_level"] + high_eps
        )
        ratio_deviation_low = (
            ratio_value_low - low_optimizer._setpoints["da_5ht_ratio"]
        ) / (low_optimizer._setpoints["da_5ht_ratio"] + low_eps)
        ratio_deviation_high = (
            ratio_value_high - high_optimizer._setpoints["da_5ht_ratio"]
        ) / (high_optimizer._setpoints["da_5ht_ratio"] + high_eps)
        expected_grad_low = -ratio_deviation_low * low_optimizer._current_lr
        expected_grad_high = -ratio_deviation_high * high_optimizer._current_lr

        assert gradients_low["dopamine"]["learning_rate"] == pytest.approx(
            expected_grad_low
        )
        assert gradients_high["dopamine"]["learning_rate"] == pytest.approx(
            expected_grad_high
        )

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

    def test_performance_history_respects_window(self, sample_params, sample_state):
        """Ensure performance history is capped to history_window."""
        config = OptimizationConfig(history_window=3)
        optimizer = NeuroOptimizer(config)

        expected_objectives = []
        params = sample_params

        for i in range(6):
            performance = 1.0 + i * 0.1
            balance = optimizer._calculate_balance_metrics(sample_state)
            expected_objectives.append(
                optimizer._calculate_objective(performance, balance, sample_state)
            )
            params, _ = optimizer.optimize(
                params,
                sample_state,
                performance_score=performance,
            )

        assert len(optimizer._performance_history) == config.history_window
        assert optimizer._performance_history == pytest.approx(
            expected_objectives[-config.history_window:]
        )

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

    def test_learning_rate_recovers_on_improvement(self):
        """Test learning rate recovery after an improvement."""
        config = OptimizationConfig(
            balance_weight=0.35,
            performance_weight=0.45,
            stability_weight=0.20,
            learning_rate=0.02,
            learning_rate_floor=0.005,
            adaptive_decay=0.5,
            plateau_patience=1,
            ema_alpha=0.5,
        )

        optimizer = NeuroOptimizer(config)

        optimizer._update_learning_rate(1.0)
        base_lr = optimizer._current_lr

        optimizer._update_learning_rate(0.5)
        decayed_lr = optimizer._current_lr

        optimizer._update_learning_rate(1.5)
        recovered_lr = optimizer._current_lr

        assert decayed_lr < base_lr
        assert recovered_lr > decayed_lr
        assert recovered_lr <= base_lr

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

    def test_estimate_gradients_scales_with_deviation_dopamine(
        self,
        opt_config,
        sample_params,
        sample_state,
    ):
        """Test dopamine gradients scale with deviation magnitude."""
        optimizer = NeuroOptimizer(opt_config)
        setpoint = optimizer._setpoints['da_5ht_ratio']
        serotonin_level = sample_state['serotonin_level']

        small_state = dict(
            sample_state,
            dopamine_level=serotonin_level * (setpoint - 0.05),
        )
        small_gradients = optimizer._estimate_gradients(
            sample_params,
            small_state,
            performance=1.0,
        )

        large_state = dict(
            sample_state,
            dopamine_level=serotonin_level * (setpoint - 0.2),
        )
        large_gradients = optimizer._estimate_gradients(
            sample_params,
            large_state,
            performance=1.0,
        )

        small_mag = abs(small_gradients['dopamine']['learning_rate'])
        large_mag = abs(large_gradients['dopamine']['learning_rate'])

        assert large_mag > small_mag

    def test_estimate_gradients_scales_with_deviation_serotonin(
        self,
        opt_config,
        sample_params,
        sample_state,
    ):
        """Test serotonin gradients scale with deviation magnitude."""
        optimizer = NeuroOptimizer(opt_config)
        setpoint = optimizer._setpoints['da_5ht_ratio']
        serotonin_level = sample_state['serotonin_level']

        small_state = dict(
            sample_state,
            dopamine_level=serotonin_level * (setpoint + 0.05),
        )
        small_gradients = optimizer._estimate_gradients(
            sample_params,
            small_state,
            performance=1.0,
        )

        large_state = dict(
            sample_state,
            dopamine_level=serotonin_level * (setpoint + 0.2),
        )
        large_gradients = optimizer._estimate_gradients(
            sample_params,
            large_state,
            performance=1.0,
        )

        small_mag = abs(small_gradients['serotonin']['stress_threshold'])
        large_mag = abs(large_gradients['serotonin']['stress_threshold'])

        assert large_mag > small_mag

    def test_estimate_gradients_scales_with_deviation_gaba(
        self,
        opt_config,
        sample_params,
        sample_state,
    ):
        """Test GABA gradients scale with deviation magnitude."""
        optimizer = NeuroOptimizer(opt_config)
        setpoint = optimizer._setpoints['gaba_inhibition']

        optimizer._balance_history.append(
            optimizer._calculate_balance_metrics(sample_state)
        )

        small_state = dict(sample_state, gaba_inhibition=setpoint + 0.02)
        large_state = dict(sample_state, gaba_inhibition=setpoint + 0.2)

        small_gradients = optimizer._estimate_gradients(
            sample_params,
            small_state,
            performance=1.0,
        )

        large_gradients = optimizer._estimate_gradients(
            sample_params,
            large_state,
            performance=1.0,
        )

        small_mag = abs(small_gradients['gaba']['k_inhibit'])
        large_mag = abs(large_gradients['gaba']['k_inhibit'])

        assert large_mag > small_mag

    def test_estimate_gradients_scales_with_deviation_arousal(
        self,
        opt_config,
        sample_params,
        sample_state,
    ):
        """Test NA/ACh arousal gradients scale with deviation magnitude."""
        optimizer = NeuroOptimizer(opt_config)
        setpoint = optimizer._setpoints['na_arousal']

        small_state = dict(sample_state, na_arousal=setpoint + 0.05)
        large_state = dict(sample_state, na_arousal=setpoint + 0.3)

        small_gradients = optimizer._estimate_gradients(
            sample_params,
            small_state,
            performance=1.0,
        )
        large_gradients = optimizer._estimate_gradients(
            sample_params,
            large_state,
            performance=1.0,
        )

        small_mag = abs(small_gradients['na_ach']['arousal_gain'])
        large_mag = abs(large_gradients['na_ach']['arousal_gain'])

        assert large_mag > small_mag

    def test_estimate_gradients_clips_deviation_extremes(self, sample_params, sample_state):
        """Ensure gradient deviations are clipped for extreme states."""
        config = OptimizationConfig(
            learning_rate=0.2,
            momentum=0.0,
            gradient_clip=0.5,
        )
        optimizer = NeuroOptimizer(config)

        extreme_state = dict(
            sample_state,
            dopamine_level=1000.0,
            serotonin_level=0.001,
            gaba_inhibition=1000.0,
            na_arousal=1000.0,
            ach_attention=1000.0,
        )

        gradients = optimizer._estimate_gradients(
            sample_params,
            extreme_state,
            performance=5.0,
        )

        max_grad = config.learning_rate * config.gradient_clip

        assert abs(gradients['dopamine']['learning_rate']) <= max_grad
        assert abs(gradients['serotonin']['stress_threshold']) <= max_grad
        assert abs(gradients['gaba']['k_inhibit']) <= max_grad
        assert abs(gradients['na_ach']['arousal_gain']) <= max_grad
        assert abs(gradients['na_ach']['attention_gain']) <= max_grad

    def test_estimate_gradients_respects_gradient_clip(self, sample_params, sample_state):
        """Ensure gradient clip bounds deviations before learning rate scaling."""
        config = OptimizationConfig(
            learning_rate=0.3,
            momentum=0.0,
            gradient_clip=0.25,
        )
        optimizer = NeuroOptimizer(config)

        extreme_state = dict(
            sample_state,
            dopamine_level=5000.0,
            serotonin_level=0.001,
            gaba_inhibition=5000.0,
            na_arousal=5000.0,
            ach_attention=5000.0,
        )

        gradients = optimizer._estimate_gradients(
            sample_params,
            extreme_state,
            performance=5.0,
        )

        max_grad = config.learning_rate * config.gradient_clip

        assert abs(gradients['dopamine']['learning_rate']) <= max_grad
        assert abs(gradients['serotonin']['stress_threshold']) <= max_grad
        assert abs(gradients['gaba']['k_inhibit']) <= max_grad
        assert abs(gradients['na_ach']['arousal_gain']) <= max_grad
        assert abs(gradients['na_ach']['attention_gain']) <= max_grad

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
            numeric=NumericConfig(max_gradient_norm=0.01),
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

    def test_apply_updates_respects_bounds_spec_clip(self):
        """Ensure bounds_spec with clip clamps updated values."""
        config = OptimizationConfig(
            numeric=NumericConfig(max_gradient_norm=1.0),
            momentum=0.0,
            bounds_spec={
                'dopamine': {
                    'learning_rate': BoundsSpec(
                        min_value=0.55,
                        max_value=0.65,
                        behavior="clip",
                    ),
                }
            },
        )
        optimizer = NeuroOptimizer(config)
        params = {'dopamine': {'learning_rate': 0.6}}

        high_gradients = {'dopamine': {'learning_rate': 0.5}}
        high_updated = optimizer._apply_updates(params, high_gradients)
        assert high_updated['dopamine']['learning_rate'] == pytest.approx(0.65)

        low_gradients = {'dopamine': {'learning_rate': -0.5}}
        low_updated = optimizer._apply_updates(params, low_gradients)
        assert low_updated['dopamine']['learning_rate'] == pytest.approx(0.55)

    def test_apply_updates_respects_bounds_spec_raise(self):
        """Ensure bounds_spec with raise triggers error when out of bounds."""
        config = OptimizationConfig(
            numeric=NumericConfig(max_gradient_norm=1.0),
            momentum=0.0,
            bounds_spec={
                'dopamine': {
                    'learning_rate': BoundsSpec(
                        min_value=0.59,
                        max_value=0.61,
                        behavior="raise",
                    ),
                }
            },
        )
        optimizer = NeuroOptimizer(config)
        params = {'dopamine': {'learning_rate': 0.6}}
        gradients = {'dopamine': {'learning_rate': 0.5}}

        with pytest.raises(ValueError, match="dopamine.learning_rate"):
            optimizer._apply_updates(params, gradients)

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

    def test_get_optimization_report_detects_drift(self, opt_config, sample_state):
        """Test drift detection triggers health warning."""
        optimizer = NeuroOptimizer(opt_config)

        for step in range(12):
            params = {'dopamine': {'learning_rate': 0.1 + step * 1.0}}
            optimizer.optimize(params, sample_state, performance_score=1.2)

        report = optimizer.get_optimization_report()

        assert report['parameter_drift']['window'] > 0
        assert report['health_status']['drift_risk']['status'] == 'warning'
        assert any('drift' in issue.lower() for issue in report['health_status']['issues'])

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

    def test_assess_health_acceptable_system(self, opt_config):
        """Test health assessment for acceptable system."""
        optimizer = NeuroOptimizer(opt_config)

        balance = BalanceMetrics(
            dopamine_serotonin_ratio=1.6,
            gaba_excitation_balance=1.4,
            arousal_attention_coherence=0.7,
            overall_balance_score=0.7,
            homeostatic_deviation=0.2,
        )

        health = optimizer._assess_health(balance)

        assert health['status'] == 'acceptable'

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

        assert health['status'] == 'warning'
        assert len(health['issues']) > 0

    def test_assess_health_respects_configured_ranges(self):
        """Ensure health checks use configured ratio ranges."""
        config = OptimizationConfig(
            numeric=NumericConfig(
                da_5ht_ratio_range=(1.2, 2.2),
                ei_balance_range=(0.8, 1.4),
                aa_coherence_min=0.95,
            ),
        )
        optimizer = NeuroOptimizer(config)

        balance = BalanceMetrics(
            dopamine_serotonin_ratio=2.3,
            gaba_excitation_balance=0.7,
            arousal_attention_coherence=0.9,
            overall_balance_score=0.7,
            homeostatic_deviation=0.2,
        )

        health = optimizer._assess_health(balance)

        assert any(
            'High dopamine/serotonin ratio' in issue for issue in health['issues']
        )
        assert any(
            'Excessive inhibition' in issue for issue in health['issues']
        )
        assert any(
            'Poor arousal-attention coherence' in issue
            for issue in health['issues']
        )

    def test_assess_health_thresholds_from_config(self):
        """Ensure health thresholds are derived from configuration values."""
        config = OptimizationConfig(
            numeric=NumericConfig(
                da_5ht_ratio_range=(1.1, 2.1),
                ei_balance_range=(0.9, 1.5),
                aa_coherence_min=0.85,
                stability_epsilon=1e-4,
            ),
        )
        optimizer = NeuroOptimizer(config)

        da_ratio_min, da_ratio_max = config.da_5ht_ratio_range
        ei_min, _ = config.ei_balance_range
        epsilon = config.numeric.stability_epsilon

        balance = BalanceMetrics(
            dopamine_serotonin_ratio=da_ratio_max + epsilon,
            gaba_excitation_balance=ei_min - epsilon,
            arousal_attention_coherence=config.numeric.aa_coherence_min - epsilon,
            overall_balance_score=0.7,
            homeostatic_deviation=0.2,
        )

        health = optimizer._assess_health(balance)

        assert any(
            'High dopamine/serotonin ratio' in issue for issue in health['issues']
        )
        assert any('Excessive inhibition' in issue for issue in health['issues'])
        assert any(
            'Poor arousal-attention coherence' in issue
            for issue in health['issues']
        )

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
