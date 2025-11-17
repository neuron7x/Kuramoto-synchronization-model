"""Implementation of the nightly regression automation."""

from __future__ import annotations

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import asyncio
import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np

from backtest.engine import walk_forward
from core.pipelines.smoke_e2e import (
    build_signal_function,
    ingest_prices,
    run_cli_analyze,
    seed_everything,
    summarise_result,
)
from core.pipelines.smoke_e2e import (
    run_backtest as run_smoke_backtest,
)
from observability.incidents import IncidentManager, IncidentRecord
from observability.notifications import NotificationDispatcher
from scripts.nightly.config import BaselineStore, MetricEvaluation
from scripts.runtime import ArtifactManager

LOGGER = logging.getLogger(__name__)
_DEFAULT_HISTORY_PATH = Path("reports/nightly/regressions/history.jsonl")


@dataclass(slots=True)
class BacktestOutcome:
    """Structured result returned by backtest scenarios."""

    name: str
    metrics: dict[str, float]
    details: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Path] = field(default_factory=dict)


@dataclass(slots=True)
class BacktestScenario:
    """Wrapper around callable runners returning :class:`BacktestOutcome`."""

    name: str
    runner: Callable[[], BacktestOutcome]

    def run(self) -> BacktestOutcome:
        return self.runner()


@dataclass(slots=True)
class E2EOutcome:
    """Structured result returned by end-to-end scenarios."""

    name: str
    metrics: dict[str, float]
    details: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Path] = field(default_factory=dict)


@dataclass(slots=True)
class E2EScenario:
    """Wrapper around callable runners returning :class:`E2EOutcome`."""

    name: str
    runner: Callable[[], E2EOutcome]

    def run(self) -> E2EOutcome:
        return self.runner()


@dataclass(slots=True, frozen=True)
class RegressionDeviation:
    """Description of a metric that breached its regression threshold."""

    stage: str
    scenario: str
    metric: str
    baseline: float
    actual: float
    absolute_degradation: float
    relative_degradation: float | None
    message: str | None


@dataclass(slots=True)
class NightlyRunSummary:
    """High-level summary produced by :class:`NightlyRegressionRunner`."""

    success: bool
    timestamp: datetime
    artifact_dir: Path
    deviations: tuple[RegressionDeviation, ...]
    incident_id: str | None = None
    history_entry: Path | None = None


def create_default_backtest_scenarios() -> tuple[BacktestScenario, ...]:
    """Return the built-in backtest battery."""

    return (
        BacktestScenario("moving_average", _run_moving_average_backtest),
        BacktestScenario("volatility_breakout", _run_volatility_breakout_backtest),
    )


def create_default_e2e_scenarios() -> tuple[E2EScenario, ...]:
    """Return the built-in end-to-end suite."""

    return (E2EScenario("smoke_pipeline", _run_smoke_pipeline),)


class NightlyRegressionRunner:
    """Coordinate nightly regression execution and reporting."""

    def __init__(
        self,
        *,
        baseline_store: BaselineStore,
        artifact_manager: ArtifactManager,
        history_path: Path | None = None,
        incident_manager: IncidentManager | None = None,
        notification_dispatcher: NotificationDispatcher | None = None,
        backtest_scenarios: Sequence[BacktestScenario] | None = None,
        e2e_scenarios: Sequence[E2EScenario] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._baseline_store = baseline_store
        self._artifact_manager = artifact_manager
        self._history_path = Path(history_path or _DEFAULT_HISTORY_PATH)
        self._incident_manager = incident_manager or IncidentManager()
        self._notification_dispatcher = notification_dispatcher
        self._backtests = tuple(
            backtest_scenarios or create_default_backtest_scenarios()
        )
        self._e2e = tuple(e2e_scenarios or create_default_e2e_scenarios())
        self._logger = logger or LOGGER

    def run(self) -> NightlyRunSummary:
        """Execute the configured scenarios and persist artefacts."""

        timestamp = datetime.now(timezone.utc)
        artifact_dir = self._artifact_manager.directory
        self._logger.info(
            "Starting nightly regression run", extra={"artifact_dir": str(artifact_dir)}
        )

        backtest_results = self._execute_backtests(artifact_dir)
        e2e_results = self._execute_e2e(artifact_dir)

        deviations = self._evaluate_results(backtest_results, e2e_results)
        incident_id: str | None = None
        if deviations:
            incident_id = self._raise_incident(timestamp, deviations, artifact_dir)

        history_entry = self._write_history(
            timestamp,
            artifact_dir,
            backtest_results,
            e2e_results,
            deviations,
            incident_id,
        )

        summary = NightlyRunSummary(
            success=not deviations,
            timestamp=timestamp,
            artifact_dir=artifact_dir,
            deviations=tuple(deviations),
            incident_id=incident_id,
            history_entry=history_entry,
        )

        self._dispatch_notifications(summary, backtest_results, e2e_results)
        return summary

    def _execute_backtests(self, artifact_dir: Path) -> list[BacktestOutcome]:
        results: list[BacktestOutcome] = []
        for scenario in self._backtests:
            start = perf_counter()
            outcome = scenario.run()
            duration = perf_counter() - start
            self._persist_stage_result(
                artifact_dir,
                stage="backtests",
                name=scenario.name,
                metrics=outcome.metrics,
                details=outcome.details,
                artifacts=outcome.artifacts,
                duration=duration,
            )
            results.append(outcome)
        return results

    def _execute_e2e(self, artifact_dir: Path) -> list[E2EOutcome]:
        results: list[E2EOutcome] = []
        for scenario in self._e2e:
            start = perf_counter()
            outcome = scenario.run()
            duration = perf_counter() - start
            self._persist_stage_result(
                artifact_dir,
                stage="e2e",
                name=scenario.name,
                metrics=outcome.metrics,
                details=outcome.details,
                artifacts=outcome.artifacts,
                duration=duration,
            )
            results.append(outcome)
        return results

    def _persist_stage_result(
        self,
        artifact_dir: Path,
        *,
        stage: str,
        name: str,
        metrics: Mapping[str, float],
        details: Mapping[str, Any],
        artifacts: Mapping[str, Path],
        duration: float,
    ) -> None:
        stage_dir = artifact_dir / stage / name
        stage_dir.mkdir(parents=True, exist_ok=True)

        summary_payload = {
            "scenario": name,
            "stage": stage,
            "metrics": _convert_metrics(metrics),
            "details": _serialise_details(details),
            "duration_seconds": round(duration, 4),
        }
        summary_path = stage_dir / "summary.json"
        summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

        for label, path in artifacts.items():
            try:
                source = Path(path)
            except TypeError:
                continue
            if not source.exists() or not source.is_file():
                continue
            destination = stage_dir / f"{label}{source.suffix}"
            try:
                shutil.copy2(source, destination)
            except OSError:
                self._logger.warning(
                    "Failed to copy artefact",
                    extra={"source": str(source), "destination": str(destination)},
                )

    def _evaluate_results(
        self,
        backtests: Iterable[BacktestOutcome],
        e2e_results: Iterable[E2EOutcome],
    ) -> list[RegressionDeviation]:
        deviations: list[RegressionDeviation] = []
        for outcome in backtests:
            deviations.extend(self._compare_with_baseline("backtests", outcome))
        for outcome in e2e_results:
            deviations.extend(self._compare_with_baseline("e2e", outcome))
        for deviation in deviations:
            self._logger.warning(
                "Regression detected",
                extra={
                    "stage": deviation.stage,
                    "scenario": deviation.scenario,
                    "metric": deviation.metric,
                    "baseline": deviation.baseline,
                    "actual": deviation.actual,
                    "relative_degradation": deviation.relative_degradation,
                    "absolute_degradation": deviation.absolute_degradation,
                    "deviation_message": deviation.message,
                },
            )
        return deviations

    def _compare_with_baseline(
        self, stage: str, outcome: BacktestOutcome | E2EOutcome
    ) -> list[RegressionDeviation]:
        entry = self._baseline_store.get_entry(stage, outcome.name)
        if entry is None:
            self._logger.debug(
                "No baseline configured",
                extra={"stage": stage, "scenario": outcome.name},
            )
            return []

        deviations: list[RegressionDeviation] = []
        for metric, baseline_value in entry.metrics.items():
            if metric not in outcome.metrics:
                continue
            threshold = entry.thresholds.get(metric)
            if threshold is None:
                continue
            actual_value = float(outcome.metrics[metric])
            evaluation: MetricEvaluation = threshold.evaluate(
                baseline_value, actual_value
            )
            if not evaluation.passed:
                deviations.append(
                    RegressionDeviation(
                        stage=stage,
                        scenario=outcome.name,
                        metric=metric,
                        baseline=float(baseline_value),
                        actual=actual_value,
                        absolute_degradation=float(evaluation.absolute_degradation),
                        relative_degradation=evaluation.relative_degradation,
                        message=evaluation.message,
                    )
                )
        return deviations

    def _raise_incident(
        self,
        timestamp: datetime,
        deviations: Sequence[RegressionDeviation],
        artifact_dir: Path,
    ) -> str:
        description_lines = [
            "Nightly regression run detected deviations beyond configured thresholds.",
            f"Artifacts: {artifact_dir}",
        ]
        metadata = {
            "timestamp": timestamp.isoformat(),
            "artifact_dir": str(artifact_dir),
            "deviations": [
                {
                    "stage": deviation.stage,
                    "scenario": deviation.scenario,
                    "metric": deviation.metric,
                    "baseline": deviation.baseline,
                    "actual": deviation.actual,
                    "absolute_degradation": deviation.absolute_degradation,
                    "relative_degradation": deviation.relative_degradation,
                    "message": deviation.message,
                }
                for deviation in deviations
            ],
        }
        record: IncidentRecord = self._incident_manager.create(
            title="Nightly regression guardrail breached",
            description="\n".join(description_lines),
            metadata=metadata,
            severity="major",
        )
        self._logger.error(
            "Incident created due to regression deviations",
            extra={
                "incident_id": record.identifier,
                "directory": str(record.directory),
            },
        )
        return record.identifier

    def _write_history(
        self,
        timestamp: datetime,
        artifact_dir: Path,
        backtests: Sequence[BacktestOutcome],
        e2e_results: Sequence[E2EOutcome],
        deviations: Sequence[RegressionDeviation],
        incident_id: str | None,
    ) -> Path:
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": timestamp.isoformat(),
            "artifact_dir": str(artifact_dir),
            "success": not deviations,
            "backtests": {
                result.name: _convert_metrics(result.metrics) for result in backtests
            },
            "e2e": {
                result.name: _convert_metrics(result.metrics) for result in e2e_results
            },
            "deviations": [
                {
                    "stage": deviation.stage,
                    "scenario": deviation.scenario,
                    "metric": deviation.metric,
                    "baseline": deviation.baseline,
                    "actual": deviation.actual,
                    "absolute_degradation": deviation.absolute_degradation,
                    "relative_degradation": deviation.relative_degradation,
                    "message": deviation.message,
                }
                for deviation in deviations
            ],
            "incident_id": incident_id,
        }
        with self._history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
        return self._history_path

    def _dispatch_notifications(
        self,
        summary: NightlyRunSummary,
        backtests: Sequence[BacktestOutcome],
        e2e_results: Sequence[E2EOutcome],
    ) -> None:
        if self._notification_dispatcher is None:
            return

        subject = (
            "Nightly regression: PASS"
            if summary.success
            else "Nightly regression: FAIL"
        )
        message = (
            f"Backtests: {len(backtests)} scenarios, E2E: {len(e2e_results)} scenarios."
            " Deviations detected."
            if not summary.success
            else " All thresholds respected."
        )
        metadata = {
            "artifact_dir": str(summary.artifact_dir),
            "timestamp": summary.timestamp.isoformat(),
            "incident_id": summary.incident_id,
            "deviation_count": len(summary.deviations),
        }
        if summary.deviations:
            metadata["deviations"] = [
                {
                    "stage": deviation.stage,
                    "scenario": deviation.scenario,
                    "metric": deviation.metric,
                    "actual": deviation.actual,
                    "baseline": deviation.baseline,
                }
                for deviation in summary.deviations
            ]

        async def _notify() -> None:
            await self._notification_dispatcher.dispatch(
                "nightly.regression",
                subject=subject,
                message=message,
                metadata=metadata,
            )
            await self._notification_dispatcher.aclose()

        asyncio.run(_notify())


def _convert_metrics(metrics: Mapping[str, float]) -> dict[str, float]:
    return {key: float(value) for key, value in metrics.items()}


def _serialise_details(details: Mapping[str, Any]) -> dict[str, Any]:
    serialised: dict[str, Any] = {}
    for key, value in details.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            serialised[key] = value
        elif isinstance(value, Path):
            serialised[key] = str(value)
        elif isinstance(value, Mapping):
            serialised[key] = _serialise_details(value)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            serialised[key] = [
                item if isinstance(item, (str, int, float, bool)) else str(item)
                for item in value
            ]
        else:
            serialised[key] = str(value)
    return serialised


def _moving_average_signal(
    prices: np.ndarray, fast: int = 10, slow: int = 40
) -> np.ndarray:
    arr = np.asarray(prices, dtype=float)
    signal = np.zeros_like(arr, dtype=float)
    if arr.size < slow:
        return signal
    fast_kernel = np.ones(fast, dtype=float) / fast
    slow_kernel = np.ones(slow, dtype=float) / slow
    fast_ma = np.convolve(arr, fast_kernel, mode="same")
    slow_ma = np.convolve(arr, slow_kernel, mode="same")
    diff = fast_ma - slow_ma
    segment = diff[slow - 1 :]
    signal[slow - 1 :] = np.where(
        segment > 0.0, 1.0, np.where(segment < 0.0, -1.0, 0.0)
    )
    previous = 0.0
    for idx in range(slow - 1, arr.size):
        if signal[idx] == 0.0:
            signal[idx] = previous
        previous = signal[idx]
    return signal


def _run_moving_average_backtest() -> BacktestOutcome:
    prices = np.loadtxt("data/sample.csv", delimiter=",", skiprows=1, usecols=1)
    result = walk_forward(
        prices,
        _moving_average_signal,
        fee=0.0005,
        strategy_name="nightly-moving-average",
    )
    performance = result.performance
    metrics = {
        "pnl": float(result.pnl),
        "max_drawdown": float(result.max_dd),
        "sharpe_ratio": (
            float(performance.sharpe_ratio)
            if performance and performance.sharpe_ratio is not None
            else 0.0
        ),
        "trades": float(result.trades),
    }
    details = {
        "latency_steps": int(result.latency_steps),
        "commission_cost": float(result.commission_cost),
        "slippage_cost": float(result.slippage_cost),
        "spread_cost": float(result.spread_cost),
        "financing_cost": float(result.financing_cost),
    }
    artifacts: dict[str, Path] = {}
    if result.report_path and result.report_path.exists():
        artifacts["performance_report"] = result.report_path
    return BacktestOutcome(
        name="moving_average", metrics=metrics, details=details, artifacts=artifacts
    )


def _volatility_breakout_signal(prices: np.ndarray) -> np.ndarray:
    arr = np.asarray(prices, dtype=float)
    signal = np.zeros_like(arr, dtype=float)
    if arr.size < 4:
        return signal
    lookback = 32
    for idx in range(1, arr.size):
        start = max(0, idx - lookback)
        window = arr[start:idx]
        delta = arr[idx] - arr[idx - 1]
        if window.size == 0:
            signal[idx] = signal[idx - 1]
            continue
        vol = np.std(np.diff(window, prepend=window[0])) or 1.0
        threshold = 0.5 * vol
        if delta > threshold:
            signal[idx] = 1.0
        elif delta < -threshold:
            signal[idx] = -1.0
        else:
            signal[idx] = signal[idx - 1]
    return signal


def _generate_volatility_path(seed: int = 1337, steps: int = 600) -> np.ndarray:
    rng = np.random.default_rng(seed)
    regime_a = rng.normal(0.0, 0.3, steps // 3)
    regime_b = rng.normal(0.0, 0.8, steps // 3)
    regime_c = rng.normal(0.0, 0.4, steps - 2 * (steps // 3))
    returns = np.concatenate((regime_a, regime_b, regime_c))
    prices = 120.0 + np.cumsum(returns)
    prices -= prices.min() - 75.0
    return prices.astype(float)


def _run_volatility_breakout_backtest() -> BacktestOutcome:
    prices = _generate_volatility_path()
    result = walk_forward(
        prices,
        _volatility_breakout_signal,
        fee=0.0008,
        strategy_name="nightly-volatility",
    )
    performance = result.performance
    metrics = {
        "pnl": float(result.pnl),
        "max_drawdown": float(result.max_dd),
        "sharpe_ratio": (
            float(performance.sharpe_ratio)
            if performance and performance.sharpe_ratio is not None
            else 0.0
        ),
        "trades": float(result.trades),
    }
    details = {
        "latency_steps": int(result.latency_steps),
        "commission_cost": float(result.commission_cost),
        "slippage_cost": float(result.slippage_cost),
        "spread_cost": float(result.spread_cost),
        "financing_cost": float(result.financing_cost),
    }
    artifacts: dict[str, Path] = {}
    if result.report_path and result.report_path.exists():
        artifacts["performance_report"] = result.report_path
    return BacktestOutcome(
        name="volatility_breakout",
        metrics=metrics,
        details=details,
        artifacts=artifacts,
    )


def _run_smoke_pipeline() -> E2EOutcome:
    seed = 20240615
    csv_path = Path("data/sample.csv")
    seed_everything(seed)
    cli_metrics = run_cli_analyze(csv_path, seed)
    ticks = ingest_prices(csv_path)
    prices = np.asarray([float(t.price) for t in ticks], dtype=float)
    signal_fn = build_signal_function(cli_metrics, window=12)
    result = run_smoke_backtest(prices, signal_fn, fee=0.0005)
    summary = summarise_result(result, ticks, cli_metrics)

    backtest_summary = summary.get("backtest", {})
    metrics = {
        "pnl": float(backtest_summary.get("pnl", 0.0)),
        "max_drawdown": float(backtest_summary.get("max_drawdown", 0.0)),
        "trades": float(backtest_summary.get("trades", 0)),
        "ingested_ticks": float(summary.get("ingested_ticks", len(ticks))),
    }
    details = {
        "seed": seed,
        "cli_metrics": _serialise_details(cli_metrics),
        "report_path": backtest_summary.get("report_path"),
    }
    artifacts: dict[str, Path] = {}
    report_path_raw = backtest_summary.get("report_path")
    if report_path_raw:
        report_path = Path(report_path_raw)
        if report_path.exists():
            artifacts["performance_report"] = report_path
    return E2EOutcome(
        name="smoke_pipeline", metrics=metrics, details=details, artifacts=artifacts
    )
