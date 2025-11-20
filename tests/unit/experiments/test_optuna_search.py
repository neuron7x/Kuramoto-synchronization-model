from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from optuna.pruners import MedianPruner
from optuna.samplers import TPESampler

from core.experiments import (
    ModelRegistry,
    OptunaSearchConfig,
    StrategyHyperparameterSearch,
)


def _objective(params: dict[str, float], *, data: np.ndarray) -> float:
    """Synthetic quadratic objective with global optimum at x=0.2."""

    target = 0.2
    candidate = float(params["x"])
    # Encourage the optimiser to explore by providing smooth gradient-like signal.
    score = -abs(candidate - target)
    # Depend on data to ensure fold-specific evaluations exercise the plumbing.
    score += 0.001 * float(np.mean(data))
    return score


def _sampler(trial) -> dict[str, float]:  # type: ignore[override]
    return {"x": trial.suggest_float("x", 0.0, 1.0)}


def test_optuna_search_logs_artifacts_and_promotes_best(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    search = StrategyHyperparameterSearch(registry)

    dataset = np.linspace(0.0, 1.0, 90, dtype=float)

    config = OptunaSearchConfig(
        experiment="test-optuna-search",
        parameter_sampler=_sampler,
        objective=_objective,
        baseline_params={"x": 0.8},
        n_trials=12,
        n_splits=3,
        n_startup_trials=3,
        promotion_threshold=0.05,
        random_seed=7,
    )

    result = search.run(data=dataset, config=config)

    assert result.best_score > result.baseline_score
    assert result.promoted is True
    assert result.improvement == result.best_score - result.baseline_score
    assert len(result.trial_history) == len(result.study.trials)
    assert isinstance(result.study.sampler, TPESampler)
    assert isinstance(result.study.pruner, MedianPruner)

    best_trial_history = max(
        result.trial_history,
        key=lambda item: (
            float("-inf") if item["value"] is None else float(item["value"])
        ),
    )
    assert len(best_trial_history["fold_scores"]) == config.n_splits

    run = registry.get_run(result.registry_run_id)
    assert "promoted" in run.tags
    assert run.parameters["best_params"]["x"] == result.best_params["x"]
    summary = run.metadata["summary"]
    assert summary["promotion"]["promoted"] is True
    assert summary["baseline"]["params"] == config.baseline_params
    assert summary["improvement"] == result.improvement

    artifact_paths = [
        artifact.absolute_path(registry.base_dir) for artifact in run.artifacts
    ]
    assert {path.name for path in artifact_paths} == {
        "study_summary.json",
        "trials_history.json",
        "best_params.json",
    }
    for path in artifact_paths:
        assert path.exists()

    summary_artifact = next(
        artifact for artifact in run.artifacts if artifact.name == "study_summary.json"
    )
    summary_payload = json.loads(
        (registry.base_dir / summary_artifact.stored_path).read_text(encoding="utf-8")
    )
    assert summary_payload["experiment"] == config.experiment
    assert summary_payload["promotion"]["promoted"] is True
