from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from observability.finops import (
    Budget,
    CostOptimisationPlan,
    FinOpsAlert,
    FinOpsController,
    ResourceUsageSample,
)


class AlertCollector:
    def __init__(self) -> None:
        self.alerts: list[FinOpsAlert] = []

    def handle_alert(self, alert: FinOpsAlert) -> None:
        self.alerts.append(alert)


def _ts(offset_hours: int) -> datetime:
    base = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    return base + timedelta(hours=offset_hours)


def test_resource_usage_sample_validation() -> None:
    timestamp = _ts(0)
    sample = ResourceUsageSample(
        resource_id="worker-a",
        timestamp=timestamp,
        cost=12.5,
        usage={"cpu_utilisation": 0.42},
    )
    assert sample.resource_id == "worker-a"
    assert sample.timestamp == timestamp

    with pytest.raises(ValueError):
        ResourceUsageSample(resource_id="", timestamp=timestamp, cost=0.0)
    with pytest.raises(ValueError):
        ResourceUsageSample(resource_id="x", timestamp=timestamp, cost=-1.0)
    with pytest.raises(ValueError):
        ResourceUsageSample(
            resource_id="x", timestamp=timestamp, cost=1.0, usage={"cpu": -0.5}
        )


def test_budget_alerts_trigger_and_reset() -> None:
    collector = AlertCollector()
    controller = FinOpsController(alert_sink=collector)
    budget = Budget(
        name="prod-core",
        limit=100.0,
        period=timedelta(hours=6),
        scope={"env": "prod"},
        alert_thresholds=(0.5, 0.8, 1.0),
    )
    controller.add_budget(budget)

    controller.record_usage(
        ResourceUsageSample(
            resource_id="node-1",
            timestamp=_ts(0),
            cost=40.0,
            usage={"cpu_utilisation": 0.55},
            metadata={"env": "prod"},
        )
    )
    assert collector.alerts == []

    controller.record_usage(
        ResourceUsageSample(
            resource_id="node-2",
            timestamp=_ts(1),
            cost=15.0,
            usage={"cpu_utilisation": 0.61},
            metadata={"env": "prod"},
        )
    )
    assert [alert.threshold for alert in collector.alerts] == [0.5]

    controller.record_usage(
        ResourceUsageSample(
            resource_id="node-3",
            timestamp=_ts(2),
            cost=30.0,
            usage={"cpu_utilisation": 0.6},
            metadata={"env": "prod"},
        )
    )
    thresholds = [alert.threshold for alert in collector.alerts]
    assert thresholds == [0.5, 0.8]

    controller.record_usage(
        ResourceUsageSample(
            resource_id="node-3",
            timestamp=_ts(3),
            cost=25.0,
            usage={"cpu_utilisation": 0.7},
            metadata={"env": "prod"},
        )
    )
    thresholds = [alert.threshold for alert in collector.alerts]
    assert thresholds == [0.5, 0.8, 1.0]
    assert collector.alerts[-1].breached is True

    # Usage falls below minimum threshold causing reset
    controller.record_usage(
        ResourceUsageSample(
            resource_id="node-1",
            timestamp=_ts(12),
            cost=5.0,
            usage={"cpu_utilisation": 0.1},
            metadata={"env": "prod"},
        )
    )
    collector.alerts.clear()
    controller.record_usage(
        ResourceUsageSample(
            resource_id="node-1",
            timestamp=_ts(13),
            cost=55.0,
            usage={"cpu_utilisation": 0.55},
            metadata={"env": "prod"},
        )
    )
    assert [alert.threshold for alert in collector.alerts] == [0.5]


def test_analyse_costs_and_recommendations() -> None:
    controller = FinOpsController()
    for idx in range(4):
        controller.record_usage(
            ResourceUsageSample(
                resource_id="db-primary",
                timestamp=_ts(idx),
                cost=35.0,
                usage={"cpu_utilisation": 0.12, "storage_gb": 200.0},
                metadata={"env": "prod"},
            )
        )

    controller.record_usage(
        ResourceUsageSample(
            resource_id="db-primary",
            timestamp=_ts(4),
            cost=90.0,
            usage={"cpu_utilisation": 0.18, "storage_gb": 200.0},
            metadata={"env": "prod"},
        )
    )

    report = controller.analyse_costs(
        timedelta(hours=6), as_of=_ts(5), metadata_filter={"env": "prod"}
    )
    assert pytest.approx(report.total_cost, rel=1e-6) == 230.0
    assert report.resource_costs == {"db-primary": 230.0}
    assert report.usage_totals["storage_gb"] == pytest.approx(1000.0)

    recommendations = controller.recommend_optimisations(
        timedelta(hours=6),
        as_of=_ts(5),
        metadata_filter={"env": "prod"},
    )
    assert any(
        rec for rec in recommendations if "rightsizing" in rec.message
    ), "Expected rightsizing recommendation"
    assert any(
        rec for rec in recommendations if "spikes" in rec.message
    ), "Expected spike investigation recommendation"


def test_generate_cost_optimisation_plan_systemic_actions() -> None:
    controller = FinOpsController()
    budget = Budget(
        name="research",
        limit=250.0,
        period=timedelta(hours=24),
        scope={"env": "research"},
        alert_thresholds=(0.5, 0.75, 1.0),
    )
    controller.add_budget(budget)

    for idx, cost in enumerate((120.0, 118.0, 119.5)):
        controller.record_usage(
            ResourceUsageSample(
                resource_id="trainer-a",
                timestamp=_ts(idx),
                cost=cost,
                usage={"gpu_utilisation": 0.42},
                metadata={
                    "env": "research",
                    "cloud": "aws",
                    "instance_type": "p4d.24xlarge",
                    "purchase_option": "on-demand",
                    "resource_kind": "gpu",
                    "model_size_gb": "45",
                    "throughput_rps": "0.25",
                    "workload_id": "alpha-llm",
                    "scaling_policy": "manual",
                    "gpu_count": "8",
                },
            )
        )

    controller.record_usage(
        ResourceUsageSample(
            resource_id="trainer-b",
            timestamp=_ts(3),
            cost=95.0,
            usage={"gpu_utilisation": 0.38},
            metadata={
                "env": "research",
                "cloud": "aws",
                "instance_type": "p4d.24xlarge",
                "purchase_option": "on-demand",
                "resource_kind": "gpu",
                "model_size_gb": "40",
                "throughput_rps": "0.22",
                "workload_id": "alpha-llm",
                "scaling_policy": "manual",
                "gpu_count": "8",
            },
        )
    )

    controller.record_usage(
        ResourceUsageSample(
            resource_id="api-service",
            timestamp=_ts(4),
            cost=45.0,
            usage={"cpu_utilisation": 0.2},
            metadata={
                "env": "research",
                "cloud": "aws",
                "instance_type": "c6i.large",
                "purchase_option": "on-demand",
                "scaling_policy": "manual",
                "workload_type": "api",
            },
        )
    )
    controller.record_usage(
        ResourceUsageSample(
            resource_id="api-service",
            timestamp=_ts(5),
            cost=45.0,
            usage={"cpu_utilisation": 0.9},
            metadata={
                "env": "research",
                "cloud": "aws",
                "instance_type": "c6i.large",
                "purchase_option": "on-demand",
                "scaling_policy": "manual",
                "workload_type": "api",
            },
        )
    )
    controller.record_usage(
        ResourceUsageSample(
            resource_id="api-service",
            timestamp=_ts(6),
            cost=45.0,
            usage={"cpu_utilisation": 0.25},
            metadata={
                "env": "research",
                "cloud": "aws",
                "instance_type": "c6i.large",
                "purchase_option": "on-demand",
                "scaling_policy": "manual",
                "workload_type": "api",
            },
        )
    )

    controller.record_usage(
        ResourceUsageSample(
            resource_id="batch-inference",
            timestamp=_ts(7),
            cost=55.0,
            usage={"cpu_utilisation": 0.3},
            metadata={
                "env": "research",
                "cloud": "gcp",
                "instance_type": "n2-standard-16",
                "purchase_option": "on-demand",
                "spot_eligible": "true",
                "workload_type": "batch",
            },
        )
    )

    controller.record_usage(
        ResourceUsageSample(
            resource_id="research-idle",
            timestamp=_ts(8),
            cost=25.0,
            usage={"cpu_utilisation": 0.0},
            metadata={
                "env": "research",
                "cloud": "aws",
                "instance_type": "t3.small",
                "purchase_option": "on-demand",
            },
        )
    )

    controller.record_usage(
        ResourceUsageSample(
            resource_id="staging-node",
            timestamp=_ts(8),
            cost=15.0,
            usage={"cpu_utilisation": 0.0},
            metadata={
                "env": "staging",
                "cloud": "aws",
                "instance_type": "t3.medium",
                "purchase_option": "on-demand",
            },
        )
    )

    plan = controller.generate_cost_optimisation_plan(
        timedelta(hours=12), metadata_filter={"env": "research"}, as_of=_ts(9)
    )

    assert isinstance(plan, CostOptimisationPlan)
    assert plan.window_start == _ts(9) - timedelta(hours=12)
    assert plan.cloud_costs["aws"] > 0.0
    assert plan.cloud_costs["gcp"] > 0.0
    assert any(key.startswith("aws:") for key in plan.instance_costs)

    profile_lookup = {
        profile.resource_id: profile for profile in plan.resource_profiles
    }
    assert profile_lookup["trainer-a"].cloud == "aws"
    assert profile_lookup["trainer-a"].purchase_option == "on-demand"

    categories = {rec.category for rec in plan.recommendations}
    expected_categories = {
        "reserved_instances",
        "gpu_sharing",
        "model_optimisation",
        "deduplication",
        "autoscaling",
        "spot",
        "budget",
        "overspend_alert",
        "cloud_profile",
        "governance",
    }
    assert expected_categories.issubset(categories)

    idle_recs = [rec for rec in plan.recommendations if rec.category == "idle_shutdown"]
    assert idle_recs, "Expected idle shutdown recommendation"

    governance_recs = [
        rec for rec in plan.recommendations if rec.category == "governance"
    ]
    assert (
        governance_recs[0]
        .metadata["next_review"]
        .startswith(str(plan.review_schedule[0].date()))
    )

    overspend = [
        rec for rec in plan.recommendations if rec.category == "overspend_alert"
    ]
    assert overspend[0].resource_id == "research"

    assert len(plan.review_schedule) == 4
