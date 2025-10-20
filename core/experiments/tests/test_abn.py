"""Tests for the production A/B/n experimentation utilities."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Mapping

import pytest

from core.experiments import (
    ABNExperiment,
    ExperimentArm,
    ExperimentSegmenter,
    Guardrail,
    MetricDefinition,
    ModelRegistry,
    StoppingPolicy,
)


@pytest.fixture()
def experiment() -> ABNExperiment:
    arms = (
        ExperimentArm("control", allocation=0.5, is_control=True),
        ExperimentArm("variant-a", allocation=0.25),
        ExperimentArm("variant-b", allocation=0.25),
    )
    metrics = (
        MetricDefinition(
            key="conversion",
            guardrail=Guardrail(metric="conversion", minimum=0.02, max_relative_drop=0.1),
        ),
        MetricDefinition(key="revenue", covariate_key="baseline_revenue"),
    )
    segmenter = ExperimentSegmenter(stratify_by=("region",))
    policy = StoppingPolicy(min_samples_per_arm=5, p_value_threshold=0.05)
    return ABNExperiment(
        "exp-prod-001",
        arms,
        metrics,
        segmenter=segmenter,
        stopping_policy=policy,
    )


def test_assignment_is_deterministic(experiment: ABNExperiment) -> None:
    attrs = {"region": "eu", "tier": "gold"}
    first = experiment.assign("user-1", attrs)
    second = experiment.assign("user-1", attrs)
    assert first == second
    assert first in {"control", "variant-a", "variant-b"}


def test_stratification_tracks_distribution(experiment: ABNExperiment) -> None:
    participants = [
        ("user-eu-1", {"region": "eu"}),
        ("user-eu-2", {"region": "eu"}),
        ("user-us-1", {"region": "us"}),
        ("user-us-2", {"region": "us"}),
    ]
    for user_id, attrs in participants:
        arm = experiment.assign(user_id, attrs)
        experiment.record_observation(
            user_id,
            metrics={"conversion": 0.03, "revenue": 120.0},
            covariates={"baseline_revenue": 100.0},
        )
        assert arm is not None

    result = experiment.evaluate()
    assert set(result.strata_balance) == {"region=eu", "region=us"}
    for stratum_counts in result.strata_balance.values():
        assert pytest.approx(sum(stratum_counts.values()), rel=1e-6) == 1.0


def test_guardrail_and_cuped_adjustments() -> None:
    class FakeRandomiser:
        def __init__(self, mapping: Mapping[str, str], control_name: str) -> None:
            self._mapping = mapping
            self._control = control_name

        @property
        def control_name(self) -> str:
            return self._control

        def assign(self, participant_id: str, _: str) -> str:
            return self._mapping[participant_id]

    arms = (
        ExperimentArm("control", allocation=0.34, is_control=True),
        ExperimentArm("variant-a", allocation=0.33),
        ExperimentArm("variant-b", allocation=0.33),
    )
    metrics = (
        MetricDefinition(
            key="conversion",
            guardrail=Guardrail(metric="conversion", minimum=0.02, max_relative_drop=0.1),
        ),
        MetricDefinition(key="revenue", covariate_key="baseline_revenue"),
    )
    mapping = {
        "u1": "control",
        "u2": "control",
        "u3": "variant-a",
        "u4": "variant-a",
        "u5": "variant-b",
        "u6": "variant-b",
    }
    experiment = ABNExperiment(
        "exp-prod-guardrail",
        arms,
        metrics,
        segmenter=ExperimentSegmenter(stratify_by=("region",)),
        randomiser=FakeRandomiser(mapping, control_name="control"),
        stopping_policy=StoppingPolicy(min_samples_per_arm=2),
    )

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    user_metrics = {
        "u1": (0.025, 120.0, 100.0),
        "u2": (0.024, 118.0, 96.0),
        "u3": (0.032, 140.0, 111.0),
        "u4": (0.034, 139.0, 108.0),
        "u5": (0.018, 90.0, 95.0),
        "u6": (0.019, 88.0, 92.0),
    }
    for idx, user_id in enumerate(mapping):
        attrs = {"region": "eu" if idx % 2 == 0 else "us"}
        arm = experiment.assign(user_id, attrs)
        conversion, revenue, baseline = user_metrics[user_id]
        experiment.record_observation(
            user_id,
            metrics={"conversion": conversion, "revenue": revenue},
            covariates={"baseline_revenue": baseline},
            timestamp=start + timedelta(hours=idx),
        )

    result = experiment.evaluate()
    conversions = [m for m in result.metrics if m.metric == "conversion"]
    assert any(not comp.guardrail_passed for comp in conversions)
    cuped_summaries = [
        stat for stat in result.arm_statistics if stat.metric == "revenue" and stat.cuped_theta is not None
    ]
    assert cuped_summaries, "Expected CUPED adjustments for revenue metric"


def test_publish_conclusions(tmp_path) -> None:
    registry_path = tmp_path / "registry"
    registry = ModelRegistry(registry_path)
    experiment = ABNExperiment(
        "exp-prod-002",
        (
            ExperimentArm("control", allocation=0.5, is_control=True),
            ExperimentArm("variant", allocation=0.5),
        ),
        (MetricDefinition(key="conversion"),),
    )
    attrs = {"region": "eu"}
    for idx in range(12):
        user_id = f"user-{idx}"
        arm = experiment.assign(user_id, attrs)
        assert arm in {"control", "variant"}
        experiment.record_observation(
            user_id,
            metrics={"conversion": 0.04 if arm == "variant" else 0.03},
        )

    result = experiment.publish_conclusions(
        registry,
        metadata={"owner": "exp-team"},
        tags={"regression"},
    )

    latest = registry.latest_run("exp-prod-002")
    assert latest is not None
    assert any(key.startswith("conversion:variant") for key in latest.metrics)
    assert result.to_dict()["metrics"]
