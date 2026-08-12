# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Behavioural coverage for analytics.code_health.models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from analytics.code_health.models import (
    DeveloperMetrics,
    FileMetrics,
    FunctionMetrics,
    RepositoryMetrics,
    RiskProfile,
    Thresholds,
    TrendInsight,
)


def _risk(score: float) -> RiskProfile:
    return RiskProfile(risk_score=score)


def _file(path: str, *, risk: float, **overrides: object) -> FileMetrics:
    base: dict[str, Any] = dict(
        path=path,
        total_lines=100,
        avg_cyclomatic_complexity=5.0,
        max_cyclomatic_complexity=8,
        functions=[],
        coupling=3,
        fan_in=1,
        fan_out=1,
        change_frequency=1,
        interface_stability=0.9,
        churn=2,
        hot_spot_score=1.0,
        risk_profile=_risk(risk),
    )
    base.update(overrides)
    return FileMetrics(**base)


def test_thresholds_defaults() -> None:
    t = Thresholds()
    assert t.max_function_length == 60
    assert t.max_cyclomatic_complexity == 10
    assert t.max_coupling == 15
    assert t.max_hotspot_churn == 20
    assert t.min_interface_stability == 0.75
    assert t.max_risk_score == 0.6


def test_thresholds_override() -> None:
    t = Thresholds(max_function_length=10, max_cyclomatic_complexity=2)
    assert t.max_function_length == 10
    assert t.max_cyclomatic_complexity == 2


def test_function_metrics_exceeds_length_true_and_false() -> None:
    long_fn = FunctionMetrics("f", "a.py", 1, 100, 3, length=61, fan_in=0, fan_out=0)
    short_fn = FunctionMetrics("f", "a.py", 1, 5, 3, length=60, fan_in=0, fan_out=0)
    assert long_fn.exceeds_length is True
    assert short_fn.exceeds_length is False


def test_function_metrics_exceeds_complexity_true_and_false() -> None:
    complex_fn = FunctionMetrics("f", "a.py", 1, 5, 11, length=5, fan_in=0, fan_out=0)
    simple_fn = FunctionMetrics("f", "a.py", 1, 5, 10, length=5, fan_in=0, fan_out=0)
    assert complex_fn.exceeds_complexity is True
    assert simple_fn.exceeds_complexity is False


def test_risk_profile_default_factories_independent() -> None:
    a = RiskProfile(risk_score=0.1)
    b = RiskProfile(risk_score=0.2)
    a.contributing_factors.append("x")
    a.recommendations.append("y")
    assert b.contributing_factors == []
    assert b.recommendations == []


def test_developer_metrics_defaults() -> None:
    dm = DeveloperMetrics(author="Ann", commits=3, files_touched=2, churn=10)
    assert dm.hotspots == []
    dm2 = DeveloperMetrics("Bob", 1, 1, 1, hotspots=["f.py"])
    assert dm2.hotspots == ["f.py"]


def test_trend_insight_fields() -> None:
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ti = TrendInsight("cx", previous=1.0, current=2.0, delta=1.0, direction="up", timestamp=ts)
    assert ti.direction == "up"
    assert ti.delta == 1.0
    assert ti.timestamp == ts


def test_exceeding_thresholds_all_violations() -> None:
    fm = _file(
        "bad.py",
        risk=0.9,
        max_cyclomatic_complexity=20,
        avg_cyclomatic_complexity=15.0,
        coupling=30,
        hot_spot_score=99.0,
        interface_stability=0.1,
    )
    violations = fm.exceeding_thresholds(Thresholds())
    assert set(violations) == {
        "max_cyclomatic_complexity",
        "avg_cyclomatic_complexity",
        "coupling",
        "hot_spot_score",
        "interface_stability",
        "risk_score",
    }
    assert violations["coupling"] == 30
    assert violations["risk_score"] == 0.9


def test_exceeding_thresholds_none() -> None:
    fm = _file("clean.py", risk=0.1)
    assert fm.exceeding_thresholds(Thresholds()) == {}


def test_repository_metrics_iter_and_most_risky() -> None:
    low = _file("low.py", risk=0.2)
    mid = _file("mid.py", risk=0.5)
    high = _file("high.py", risk=0.9)
    repo = RepositoryMetrics(
        generated_at=datetime.now(timezone.utc),
        files={"low.py": low, "mid.py": mid, "high.py": high},
        thresholds=Thresholds(),
        risk_hotspots=[low, mid, high],
    )
    assert list(repo.iter_files()) == [low, mid, high]
    ordered = repo.most_risky()
    assert [fm.path for fm in ordered] == ["high.py", "mid.py", "low.py"]
    assert repo.most_risky(limit=1) == [high]


def test_repository_metrics_defaults_empty() -> None:
    repo = RepositoryMetrics(
        generated_at=datetime.now(timezone.utc),
        files={},
        thresholds=Thresholds(),
    )
    assert repo.risk_hotspots == []
    assert repo.trends == []
    assert repo.developer_metrics == []
    assert list(repo.iter_files()) == []
    assert repo.most_risky() == []
