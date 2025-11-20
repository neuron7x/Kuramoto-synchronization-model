"""Unit tests for nightly regression orchestration."""

from __future__ import annotations

import json
from pathlib import Path

from observability.incidents import IncidentManager
from scripts.nightly.config import BaselineStore, MetricThreshold
from scripts.nightly.regression import (
    BacktestOutcome,
    BacktestScenario,
    E2EOutcome,
    E2EScenario,
    NightlyRegressionRunner,
)
from scripts.runtime import create_artifact_manager


class _StubDispatcher:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, str, dict | None]] = []
        self.closed = False

    async def dispatch(
        self,
        event: str,
        *,
        subject: str,
        message: str,
        metadata: dict | None = None,
    ) -> None:
        self.events.append((event, subject, message, metadata))

    async def aclose(self) -> None:
        self.closed = True


def _write_baseline(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "baselines.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def test_metric_threshold_evaluation() -> None:
    threshold = MetricThreshold(
        higher_is_better=True, max_relative_change=0.1, max_absolute_change=5.0
    )
    result_ok = threshold.evaluate(100.0, 95.5)
    assert result_ok.passed
    assert result_ok.message is None

    result_fail = threshold.evaluate(100.0, 80.0)
    assert not result_fail.passed
    assert result_fail.relative_degradation is not None
    assert result_fail.relative_degradation > 0.1

    dd_threshold = MetricThreshold(
        higher_is_better=False, max_relative_change=0.2, max_absolute_change=1.0
    )
    drawdown_ok = dd_threshold.evaluate(-4.0, -4.5)
    assert drawdown_ok.passed
    drawdown_fail = dd_threshold.evaluate(-4.0, -5.8)
    assert not drawdown_fail.passed


def test_runner_records_history_and_notifications(tmp_path: Path) -> None:
    baseline_path = _write_baseline(
        tmp_path,
        {
            "backtests": {
                "alpha": {
                    "baseline": {"pnl": 1.0},
                    "thresholds": {
                        "pnl": {"higher_is_better": True, "max_relative_change": 0.2}
                    },
                }
            },
            "e2e": {
                "omega": {
                    "baseline": {"pnl": 2.0},
                    "thresholds": {
                        "pnl": {"higher_is_better": True, "max_relative_change": 0.5}
                    },
                }
            },
        },
    )

    def _backtest_runner() -> BacktestOutcome:
        return BacktestOutcome(
            name="alpha", metrics={"pnl": 1.1}, details={"trades": 3}
        )

    def _e2e_runner() -> E2EOutcome:
        return E2EOutcome(name="omega", metrics={"pnl": 2.5}, details={})

    artifact_manager = create_artifact_manager(
        "test-nightly", root=tmp_path / "artifacts"
    )
    dispatcher = _StubDispatcher()
    incident_root = tmp_path / "incidents"

    runner = NightlyRegressionRunner(
        baseline_store=BaselineStore(baseline_path),
        artifact_manager=artifact_manager,
        history_path=tmp_path / "history.jsonl",
        incident_manager=IncidentManager(incident_root),
        notification_dispatcher=dispatcher,
        backtest_scenarios=(BacktestScenario("alpha", _backtest_runner),),
        e2e_scenarios=(E2EScenario("omega", _e2e_runner),),
    )

    summary = runner.run()

    assert summary.success
    assert summary.incident_id is None
    assert dispatcher.events
    assert dispatcher.closed
    assert summary.artifact_dir.exists()
    assert (tmp_path / "history.jsonl").exists()
    assert not any(incident_root.rglob("summary.json"))


def test_runner_triggers_incident_on_regression(tmp_path: Path) -> None:
    baseline_path = _write_baseline(
        tmp_path,
        {
            "backtests": {
                "alpha": {
                    "baseline": {"pnl": 10.0},
                    "thresholds": {
                        "pnl": {"higher_is_better": True, "max_relative_change": 0.1}
                    },
                }
            },
            "e2e": {
                "omega": {
                    "baseline": {"pnl": 12.0},
                    "thresholds": {
                        "pnl": {"higher_is_better": True, "max_relative_change": 0.1}
                    },
                }
            },
        },
    )

    def _backtest_runner() -> BacktestOutcome:
        return BacktestOutcome(name="alpha", metrics={"pnl": 1.0}, details={})

    def _e2e_runner() -> E2EOutcome:
        return E2EOutcome(name="omega", metrics={"pnl": 1.0}, details={})

    artifact_manager = create_artifact_manager(
        "test-nightly", root=tmp_path / "artifacts"
    )
    dispatcher = _StubDispatcher()
    incident_root = tmp_path / "incidents"

    runner = NightlyRegressionRunner(
        baseline_store=BaselineStore(baseline_path),
        artifact_manager=artifact_manager,
        history_path=tmp_path / "history.jsonl",
        incident_manager=IncidentManager(incident_root),
        notification_dispatcher=dispatcher,
        backtest_scenarios=(BacktestScenario("alpha", _backtest_runner),),
        e2e_scenarios=(E2EScenario("omega", _e2e_runner),),
    )

    summary = runner.run()

    assert not summary.success
    assert summary.incident_id is not None
    assert dispatcher.events
    assert dispatcher.closed
    incident_files = list(incident_root.rglob("summary.json"))
    assert incident_files, "incident summary should have been created"
