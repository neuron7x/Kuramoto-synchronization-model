# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Behavioural coverage for analytics.code_health.aggregator.

Git shell-outs are made hermetic by patching ``subprocess.run`` on the
analyzers module (for ``collect``) or by patching the analyzer methods /
``_run`` directly. No real git process is spawned.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, cast

import pytest
from fastapi.testclient import TestClient

from analytics.code_health import analyzers
from analytics.code_health.aggregator import CodeMetricAggregator
from analytics.code_health.models import (
    DeveloperMetrics,
    FileMetrics,
    FunctionMetrics,
    RepositoryMetrics,
    RiskProfile,
    Thresholds,
    TrendInsight,
)


class _FakeCompleted:
    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = ""
        self.returncode = returncode


@pytest.fixture()
def empty_git(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force every git shell-out to return empty output."""

    monkeypatch.setattr(
        analyzers.subprocess,
        "run",
        lambda *a, **k: _FakeCompleted(""),
    )


# ---------------------------------------------------------------------------
# helpers to build metrics without running git
# ---------------------------------------------------------------------------


def _function() -> FunctionMetrics:
    return FunctionMetrics(
        name="do_work",
        file_path="core/engine.py",
        start_line=1,
        end_line=20,
        cyclomatic_complexity=12,
        length=20,
        fan_in=3,
        fan_out=2,
    )


def _risky_file() -> FileMetrics:
    return FileMetrics(
        path="core/engine.py",
        total_lines=200,
        avg_cyclomatic_complexity=14.0,
        max_cyclomatic_complexity=20,
        functions=[_function()],
        coupling=25,
        fan_in=3,
        fan_out=2,
        change_frequency=8,
        interface_stability=0.4,
        churn=90,
        hot_spot_score=55.0,
        risk_profile=RiskProfile(
            risk_score=0.92,
            contributing_factors=["High average cyclomatic complexity"],
            recommendations=["Break large functions into smaller units and add focused tests."],
        ),
    )


def _clean_file() -> FileMetrics:
    return FileMetrics(
        path="core/util.py",
        total_lines=30,
        avg_cyclomatic_complexity=2.0,
        max_cyclomatic_complexity=3,
        functions=[],
        coupling=1,
        fan_in=0,
        fan_out=0,
        change_frequency=0,
        interface_stability=0.99,
        churn=1,
        hot_spot_score=1.0,
        risk_profile=RiskProfile(risk_score=0.05),
    )


def _repo_metrics() -> RepositoryMetrics:
    risky = _risky_file()
    clean = _clean_file()
    return RepositoryMetrics(
        generated_at=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
        files={"core/engine.py": risky, "core/util.py": clean},
        thresholds=Thresholds(),
        risk_hotspots=[risky, clean],
        trends=[
            TrendInsight(
                metric="core/engine.py",
                previous=10.0,
                current=14.0,
                delta=4.0,
                direction="up",
                timestamp=datetime(2026, 3, 1, tzinfo=timezone.utc),
            )
        ],
        developer_metrics=[
            DeveloperMetrics(author="Ann", commits=5, files_touched=3, churn=120, hotspots=["a.py"])
        ],
    )


# ---------------------------------------------------------------------------
# collect (full orchestration, hermetic git)
# ---------------------------------------------------------------------------


def _seed_repo(root: Path) -> None:
    (root / "pkg").mkdir()
    (root / "pkg" / "mod.py").write_text(
        "import os\n\n"
        "def handler(x):\n"
        "    if x:\n"
        "        return os.getpid()\n"
        "    return helper()\n\n"
        "def helper():\n"
        "    return 1\n",
        encoding="utf-8",
    )
    # A file inside a venv dir must be excluded from discovery.
    (root / "venv").mkdir()
    (root / "venv" / "ignored.py").write_text("x = 1\n", encoding="utf-8")


def test_collect_builds_repository_metrics(tmp_path: Path, empty_git: None) -> None:
    _seed_repo(tmp_path)
    agg = CodeMetricAggregator(tmp_path)
    metrics = agg.collect()
    assert "pkg/mod.py" in metrics.files
    # venv file excluded
    assert all("venv" not in p for p in metrics.files)
    engine = metrics.files["pkg/mod.py"]
    assert engine.total_lines > 0
    assert len(engine.functions) == 2
    assert agg.history_file.exists()
    # no git history -> no developers, stability defaults to 1.0
    assert metrics.developer_metrics == []
    assert engine.interface_stability == 1.0


def test_collect_second_run_produces_trends(tmp_path: Path, empty_git: None) -> None:
    _seed_repo(tmp_path)
    agg = CodeMetricAggregator(tmp_path)
    agg.collect()  # writes baseline snapshot
    # Increase complexity so avg changes -> a trend appears.
    (tmp_path / "pkg" / "mod.py").write_text(
        "def handler(x):\n"
        "    if x:\n"
        "        if x > 1:\n"
        "            return 1\n"
        "    for i in range(3):\n"
        "        pass\n"
        "    return 0\n",
        encoding="utf-8",
    )
    metrics = agg.collect()
    assert any(t.metric == "pkg/mod.py" for t in metrics.trends)


# ---------------------------------------------------------------------------
# export_csv
# ---------------------------------------------------------------------------


def test_export_csv(tmp_path: Path) -> None:
    metrics = _repo_metrics()
    out = tmp_path / "metrics.csv"
    CodeMetricAggregator(tmp_path).export_csv(metrics, out)
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert {r["path"] for r in rows} == {"core/engine.py", "core/util.py"}
    engine_row = next(r for r in rows if r["path"] == "core/engine.py")
    assert engine_row["risk_score"] == "0.92"
    assert engine_row["avg_cyclomatic_complexity"] == "14.00"
    assert engine_row["interface_stability"] == "0.40"


# ---------------------------------------------------------------------------
# build_pr_report
# ---------------------------------------------------------------------------


def test_build_pr_report_no_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    agg = CodeMetricAggregator(tmp_path)
    monkeypatch.setattr(agg, "_changed_files", lambda base_ref: [])
    assert agg.build_pr_report(_repo_metrics()) == "No code changes detected against the baseline."


def test_build_pr_report_with_violations_and_recs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agg = CodeMetricAggregator(tmp_path)
    monkeypatch.setattr(
        agg,
        "_changed_files",
        lambda base_ref: ["core/engine.py", "core/util.py", "not/tracked.py"],
    )
    report = agg.build_pr_report(_repo_metrics())
    assert "### Code Health Summary" in report
    assert "**core/engine.py**" in report
    assert "Risk score: 0.92" in report
    assert "High average cyclomatic complexity" in report
    assert "Threshold alerts:" in report
    assert "Refactoring guidance:" in report
    # clean file present but stable, no alerts / guidance
    assert "**core/util.py**" in report
    assert "stable" in report
    # untracked file skipped
    assert "not/tracked.py" not in report


# ---------------------------------------------------------------------------
# build_dashboard_payload
# ---------------------------------------------------------------------------


def test_build_dashboard_payload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    agg = CodeMetricAggregator(tmp_path)
    monkeypatch.setattr(agg.git, "hot_files", lambda: [("core/engine.py", 9)])
    payload = cast("dict[str, Any]", agg.build_dashboard_payload(_repo_metrics()))
    assert payload["generated_at"].startswith("2026-03-01")
    assert payload["hot_files"] == [("core/engine.py", 9)]
    assert len(payload["risk_hotspots"]) == 2
    assert payload["developers"][0]["author"] == "Ann"
    assert payload["trends"][0]["direction"] == "up"


# ---------------------------------------------------------------------------
# create_api + FastAPI TestClient
# ---------------------------------------------------------------------------


def test_create_api_endpoints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    agg = CodeMetricAggregator(tmp_path)
    monkeypatch.setattr(agg.git, "hot_files", lambda: [("core/engine.py", 4)])
    app = agg.create_api(_repo_metrics())
    client = TestClient(app)

    files = client.get("/metrics/files")
    assert files.status_code == 200
    assert {f["path"] for f in files.json()} == {"core/engine.py", "core/util.py"}

    found = client.get("/metrics/files/core/engine.py")
    assert found.json()["risk_profile"]["score"] == 0.92

    missing = client.get("/metrics/files/does/not/exist.py")
    assert missing.json() == {"error": "File not found"}

    devs = client.get("/metrics/developers")
    assert devs.json()[0]["author"] == "Ann"

    hot = client.get("/metrics/hot-files")
    assert hot.json() == [["core/engine.py", 4]]

    trends = client.get("/metrics/trends")
    assert trends.json()[0]["metric"] == "core/engine.py"


# ---------------------------------------------------------------------------
# render_widget
# ---------------------------------------------------------------------------


def test_render_widget(tmp_path: Path) -> None:
    html = CodeMetricAggregator(tmp_path).render_widget(_repo_metrics(), theme="dark")
    assert 'data-theme="dark"' in html
    assert "core/engine.py" in html


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------


def test_safe_line_count_ok_and_binary(tmp_path: Path) -> None:
    agg = CodeMetricAggregator(tmp_path)
    good = tmp_path / "good.py"
    good.write_text("a\nb\nc\n", encoding="utf-8")
    assert agg._safe_line_count(good) == 3
    bad = tmp_path / "bad.bin"
    bad.write_bytes(b"\xff\xfe\x00\x01 invalid utf8 \xff")
    assert agg._safe_line_count(bad) == 0


def test_identify_hotspots_filters_and_sorts(tmp_path: Path) -> None:
    agg = CodeMetricAggregator(tmp_path)
    risky = _risky_file()  # hot_spot_score 55 > 20
    clean = _clean_file()  # hot_spot_score 1 -> excluded
    hotspots = agg._identify_hotspots({"a": risky, "b": clean})
    assert hotspots == [risky]


def test_changed_files_success_and_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    agg = CodeMetricAggregator(tmp_path)

    def ok_run(*args: str, check: bool = False) -> _FakeCompleted:
        return _FakeCompleted("core/a.py\nREADME.md\n  core/b.py  \n", returncode=0)

    monkeypatch.setattr(agg.git, "_run", ok_run)
    assert agg._changed_files("origin/main") == ["core/a.py", "core/b.py"]

    def fail_run(*args: str, check: bool = False) -> _FakeCompleted:
        return _FakeCompleted("", returncode=1)

    monkeypatch.setattr(agg.git, "_run", fail_run)
    assert agg._changed_files("origin/main") == []


def test_discover_files_excludes_non_files(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "pkgdir.py").mkdir()  # a directory that matches the glob
    agg = CodeMetricAggregator(tmp_path)
    discovered = agg._discover_files()
    names = {p.name for p in discovered}
    assert "a.py" in names
    assert "pkgdir.py" not in names


def test_serialize_file_metric_shape(tmp_path: Path) -> None:
    agg = CodeMetricAggregator(tmp_path)
    data = cast("dict[str, Any]", agg._serialize_file_metric(_risky_file()))
    assert data["path"] == "core/engine.py"
    assert data["risk_profile"]["score"] == 0.92
    assert data["functions"][0]["name"] == "do_work"


def test_default_history_file_and_thresholds(tmp_path: Path) -> None:
    agg = CodeMetricAggregator(tmp_path)
    assert agg.history_file == tmp_path / ".code_metrics_history.json"
    assert isinstance(agg.thresholds, Thresholds)
    custom = CodeMetricAggregator(
        tmp_path, history_file=tmp_path / "h.json", thresholds=Thresholds(max_coupling=99)
    )
    assert custom.history_file == tmp_path / "h.json"
    assert custom.thresholds.max_coupling == 99
