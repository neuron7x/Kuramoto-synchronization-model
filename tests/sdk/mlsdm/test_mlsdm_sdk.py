"""Tests for MLSDM SDK public API."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from tradepulse.sdk.mlsdm import (
    MLSDM,
    BiomarkerState,
    DecisionState,
    FHMCConfig,
    MLSDMConfig,
    OptimizationResult,
    OptimizerConfig,
    ReplayTransition,
    create_fhmc,
    create_optimizer,
    create_replay_engine,
)


class TestFHMCConfig:
    """Tests for FHMCConfig dataclass."""

    def test_default_config(self) -> None:
        """Default config creates valid instance."""
        config = FHMCConfig()
        assert config.alpha_target == (0.5, 1.5)
        assert config.orexin["k1"] == 1.0
        assert config.threat["w_dd"] == 0.5

    def test_to_dict(self) -> None:
        """Config converts to dictionary for FHMC init."""
        config = FHMCConfig()
        d = config.to_dict()
        assert "alpha_target" in d
        assert "orexin" in d
        assert "threat" in d
        assert "flipflop" in d
        assert "mfs" in d

    def test_from_dict(self) -> None:
        """Config can be created from dictionary."""
        data = {
            "alpha_target": [0.3, 1.2],
            "orexin": {"k1": 0.8, "k2": 0.6, "k3": 0.2},
        }
        config = FHMCConfig.from_dict(data)
        assert config.alpha_target == (0.3, 1.2)
        assert config.orexin["k1"] == 0.8

    def test_from_yaml(self, tmp_path: Path) -> None:
        """Config can be loaded from YAML file."""
        yaml_content = """
fhmc:
  alpha_target: [0.4, 1.3]
  orexin:
    k1: 0.9
    k2: 0.5
    k3: 0.1
"""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(yaml_content)

        config = FHMCConfig.from_yaml(yaml_file)
        assert config.alpha_target == (0.4, 1.3)
        assert config.orexin["k1"] == 0.9


class TestMLSDMConfig:
    """Tests for MLSDMConfig dataclass."""

    def test_default(self) -> None:
        """Default config is valid."""
        config = MLSDMConfig.default()
        assert config.fhmc is not None
        assert config.agent is None
        assert config.optimizer is None

    def test_from_yaml_full(self, tmp_path: Path) -> None:
        """Full config can be loaded from YAML."""
        yaml_content = """
fhmc:
  alpha_target: [0.5, 1.5]
  orexin:
    k1: 1.0
    k2: 0.7
    k3: 0.3

agent:
  state_dim: 8
  action_dim: 2
  lr: 0.001
  device: cpu

optimizer:
  dim: 3
  pack: 10
  iters: 50
"""
        yaml_file = tmp_path / "full_config.yaml"
        yaml_file.write_text(yaml_content)

        config = MLSDMConfig.from_yaml(yaml_file)
        assert config.fhmc.orexin["k1"] == 1.0
        assert config.agent is not None
        assert config.agent.state_dim == 8
        assert config.optimizer is not None
        assert config.optimizer.dim == 3


class TestCreateFHMC:
    """Tests for create_fhmc factory function."""

    def test_create_with_defaults(self) -> None:
        """FHMC creates with default config."""
        fhmc = create_fhmc()
        assert hasattr(fhmc, "state")
        assert fhmc.state in ("WAKE", "SLEEP")

    def test_create_with_config(self) -> None:
        """FHMC creates with custom config."""
        config = FHMCConfig(alpha_target=(0.6, 1.4))
        fhmc = create_fhmc(config)
        assert fhmc.cfg["alpha_target"] == [0.6, 1.4]

    def test_compute_orexin(self) -> None:
        """FHMC computes orexin correctly."""
        fhmc = create_fhmc()
        orexin = fhmc.compute_orexin(exp_return=0.1, novelty=0.5, load=0.2)
        assert 0.0 <= orexin <= 1.0

    def test_compute_threat(self) -> None:
        """FHMC computes threat correctly."""
        fhmc = create_fhmc()
        threat = fhmc.compute_threat(maxdd=0.1, volshock=0.3, cp_score=0.2)
        assert 0.0 <= threat <= 1.0

    def test_flipflop_step(self) -> None:
        """FHMC flipflop transitions state."""
        fhmc = create_fhmc()
        state = fhmc.flipflop_step()
        assert state in ("WAKE", "SLEEP")

    def test_next_window_seconds(self) -> None:
        """FHMC returns positive window size."""
        fhmc = create_fhmc()
        window = fhmc.next_window_seconds()
        assert window > 0


class TestCreateOptimizer:
    """Tests for create_optimizer factory function."""

    def test_create_optimizer(self) -> None:
        """Optimizer creates successfully."""

        def objective(x: np.ndarray) -> float:
            return float(np.sum(x**2))

        optimizer = create_optimizer(
            objective=objective,
            dim=3,
            bounds=([0, 0, 0], [1, 1, 1]),
        )
        assert optimizer is not None

    def test_optimize(self) -> None:
        """Optimizer finds minimum."""
        target = np.array([0.5, 0.5, 0.5])

        def objective(x: np.ndarray) -> float:
            return float(np.sum((x - target) ** 2))

        config = OptimizerConfig(
            dim=3,
            lb=[0, 0, 0],
            ub=[1, 1, 1],
            pack=10,
            iters=20,
        )
        optimizer = create_optimizer(
            objective=objective,
            dim=3,
            bounds=([0, 0, 0], [1, 1, 1]),
            config=config,
        )
        best_params, best_score = optimizer.optimize()

        assert best_params.shape == (3,)
        assert best_score >= 0


class TestCreateReplayEngine:
    """Tests for create_replay_engine factory function."""

    def test_create_engine(self) -> None:
        """Replay engine creates successfully."""
        engine = create_replay_engine(capacity=1000)
        assert len(engine) == 0

    def test_observe_and_sample(self) -> None:
        """Engine stores and samples transitions."""
        engine = create_replay_engine(capacity=100)

        state = np.zeros(4)
        action = np.ones(2)

        for i in range(10):
            priority = engine.observe_transition(
                state=state + i,
                action=action,
                reward=float(i) * 0.1,
                next_state=state + i + 1,
                td_error=0.1,
            )
            assert priority >= 0

        assert len(engine) == 10

        batch = engine.sample(batch_size=5)
        assert len(batch) == 5


class TestMLSDMFacade:
    """Tests for MLSDM facade class."""

    def test_default(self) -> None:
        """MLSDM creates with defaults."""
        mlsdm = MLSDM.default()
        assert mlsdm.fhmc is not None
        assert mlsdm.replay_engine is not None

    def test_get_biomarkers(self) -> None:
        """MLSDM returns biomarker state."""
        mlsdm = MLSDM.default()
        biomarkers = mlsdm.get_biomarkers()

        assert isinstance(biomarkers, BiomarkerState)
        assert 0.0 <= biomarkers.orexin <= 1.0
        assert 0.0 <= biomarkers.threat <= 1.0
        assert biomarkers.state in ("WAKE", "SLEEP")

    def test_get_decision_state(self) -> None:
        """MLSDM returns decision state."""
        mlsdm = MLSDM.default()
        state = mlsdm.get_decision_state()

        assert isinstance(state, DecisionState)
        assert state.window_seconds > 0

    def test_compute_drive(self) -> None:
        """MLSDM computes drive from market conditions."""
        mlsdm = MLSDM.default()
        biomarkers = mlsdm.compute_drive(
            exp_return=0.05,
            novelty=0.3,
            load=0.2,
            maxdd=0.1,
            volshock=0.5,
            cp_score=0.2,
        )

        assert isinstance(biomarkers, BiomarkerState)
        assert 0.0 <= biomarkers.orexin <= 1.0
        assert 0.0 <= biomarkers.threat <= 1.0

    def test_next_window(self) -> None:
        """MLSDM returns next window size."""
        mlsdm = MLSDM.default()
        window = mlsdm.next_window()
        assert window > 0

    def test_observe_and_sample(self) -> None:
        """MLSDM stores and samples transitions."""
        mlsdm = MLSDM.default()

        state = np.zeros(4)
        action = np.ones(2)

        for i in range(10):
            mlsdm.observe(
                state=state + i,
                action=action,
                reward=float(i) * 0.1,
                next_state=state + i + 1,
                td_error=0.1,
            )

        batch = mlsdm.sample(batch_size=5)
        assert len(batch) == 5
        assert all(isinstance(t, ReplayTransition) for t in batch)

    def test_optimize(self) -> None:
        """MLSDM runs optimization."""
        mlsdm = MLSDM.default()

        target = np.array([0.5, 0.5])

        def objective(x: np.ndarray) -> float:
            return float(np.sum((x - target) ** 2))

        result = mlsdm.optimize(
            objective=objective,
            dim=2,
            bounds=([0, 0], [1, 1]),
            config=OptimizerConfig(dim=2, lb=[0, 0], ub=[1, 1], pack=5, iters=10),
        )

        assert isinstance(result, OptimizationResult)
        assert result.best_params.shape == (2,)
        assert result.best_score >= 0

    def test_act_requires_agent(self) -> None:
        """MLSDM.act raises without agent."""
        mlsdm = MLSDM.default()

        with pytest.raises(RuntimeError, match="Agent not initialized"):
            mlsdm.act(np.zeros(4))

    def test_learn_requires_agent(self) -> None:
        """MLSDM.learn raises without agent."""
        mlsdm = MLSDM.default()

        with pytest.raises(RuntimeError, match="Agent not initialized"):
            mlsdm.learn(
                state=np.zeros(4),
                action=np.zeros(2),
                reward=0.1,
                next_state=np.zeros(4),
                done=False,
            )


class TestContracts:
    """Tests for MLSDM data contracts."""

    def test_biomarker_state_immutable(self) -> None:
        """BiomarkerState is frozen."""
        state = BiomarkerState(
            orexin=0.5,
            threat=0.3,
            state="WAKE",
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            state.orexin = 0.6  # type: ignore[misc]

    def test_optimization_result_to_dict(self) -> None:
        """OptimizationResult converts to dict."""
        result = OptimizationResult(
            best_params=np.array([0.5, 0.5]),
            best_score=0.1,
            iterations=100,
            pack_size=20,
        )

        d = result.to_dict()
        assert d["best_params"] == [0.5, 0.5]
        assert d["best_score"] == 0.1
        assert d["iterations"] == 100
        assert d["pack_size"] == 20

    def test_replay_transition_immutable(self) -> None:
        """ReplayTransition is frozen."""
        transition = ReplayTransition(
            state=np.zeros(4),
            action=np.ones(2),
            reward=0.1,
            next_state=np.zeros(4),
            priority=0.5,
            cp_score=0.2,
        )

        with pytest.raises(Exception):
            transition.reward = 0.2  # type: ignore[misc]
