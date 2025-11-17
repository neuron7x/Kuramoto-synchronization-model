"""Composable building blocks for the TradePulse smoke E2E pipeline."""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, MutableMapping, Sequence

import numpy as np

from backtest.engine import Result, walk_forward
from core.data.ingestion import DataIngestor, Ticker

REPO_ROOT = Path(__file__).resolve().parents[2]

AnalyzeRunner = Callable[[Path, int], Mapping[str, Any]]
IngestRunner = Callable[[Path], Sequence[Ticker]]
SignalBuilder = Callable[[Mapping[str, Any], int], Callable[[np.ndarray], np.ndarray]]
BacktestRunner = Callable[
    [np.ndarray, Callable[[np.ndarray], np.ndarray], float], Result
]
ArtifactWriter = Callable[[Mapping[str, Any], Path], Path]


def seed_everything(seed: int) -> None:
    """Seed Python and NumPy RNGs for determinism."""

    os.environ.setdefault("PYTHONHASHSEED", str(seed))
    random.seed(seed)
    np.random.seed(seed)


def _with_pythonpath(env: MutableMapping[str, str]) -> MutableMapping[str, str]:
    pythonpath = env.get("PYTHONPATH")
    root = str(REPO_ROOT)
    if pythonpath:
        if root not in pythonpath.split(":"):
            env["PYTHONPATH"] = f"{root}:{pythonpath}"
    else:
        env["PYTHONPATH"] = root
    return env


def run_cli_analyze(csv_path: Path, seed: int) -> dict[str, Any]:
    """Execute ``interfaces.cli analyze`` and return the parsed JSON payload."""

    env = _with_pythonpath(os.environ.copy())
    env.setdefault("PYTHONHASHSEED", str(seed))
    env["TRADEPULSE_SMOKE_SEED"] = str(seed)
    cmd = [
        sys.executable,
        "-m",
        "interfaces.cli",
        "analyze",
        "--csv",
        str(csv_path),
    ]
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=env,
        )
    except FileNotFoundError as exc:  # pragma: no cover - defensive guard
        raise RuntimeError(
            "Python executable not found while running CLI analyze"
        ) from exc
    output = result.stdout.strip()
    if not output:
        raise RuntimeError("CLI analyze produced no output")
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse CLI analyze JSON: {output}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("CLI analyze returned a non-object payload")
    return payload


def ingest_prices(csv_path: Path) -> list[Ticker]:
    """Load tick data from ``csv_path`` using :class:`DataIngestor`."""

    ingestor = DataIngestor(allowed_roots=[csv_path.resolve().parent])
    ticks: list[Ticker] = []
    ingestor.historical_csv(
        str(csv_path),
        ticks.append,
        required_fields=("ts", "price", "volume"),
    )
    if not ticks:
        raise RuntimeError("No ticks ingested from CSV")
    return ticks


def build_signal_function(
    metrics: Mapping[str, Any],
    window: int,
) -> Callable[[np.ndarray], np.ndarray]:
    """Construct a deterministic momentum signal informed by indicator metrics."""

    delta_entropy = float(metrics.get("delta_H", 0.0))
    kuramoto_bias = float(metrics.get("kappa_mean", 0.0))

    def _signal(prices: np.ndarray) -> np.ndarray:
        if prices.size == 0:
            return np.array([], dtype=float)
        shifted = np.roll(prices, 1)
        shifted[0] = prices[0]
        momentum = prices - shifted
        if window > 1 and momentum.size >= window:
            kernel = np.ones(window) / window
            smoothed = np.convolve(momentum, kernel, mode="same")
        else:
            smoothed = momentum
        scale = float(np.std(smoothed)) or 1.0
        normalized = smoothed / scale
        bias = 0.25 if delta_entropy < 0 else -0.25
        curvature = -0.1 if kuramoto_bias < 0 else 0.1
        combined = normalized + bias + curvature
        signals = np.where(
            combined > 0.15,
            1.0,
            np.where(combined < -0.15, -1.0, 0.0),
        )
        signals = signals.astype(float)
        signals[0] = 0.0
        return signals

    return _signal


def run_backtest(
    prices: np.ndarray,
    signal_fn: Callable[[np.ndarray], np.ndarray],
    fee: float,
) -> Result:
    """Execute the reference walk-forward backtest."""

    return walk_forward(prices, signal_fn, fee=fee, strategy_name="smoke_e2e")


def summarise_result(
    result: Result,
    ticks: Sequence[Ticker],
    metrics: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a JSON-serialisable summary for reporting and persistence."""

    report_path = result.report_path
    report_payload: Mapping[str, Any] | None = None
    if report_path and report_path.exists():
        report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    return {
        "ingested_ticks": len(ticks),
        "cli_metrics": dict(metrics),
        "backtest": {
            "pnl": result.pnl,
            "max_drawdown": result.max_dd,
            "trades": result.trades,
            "report_path": str(report_path) if report_path else None,
            "report": report_payload,
        },
    }


def write_summary(summary: Mapping[str, Any], output_dir: Path) -> Path:
    """Persist ``summary`` as ``summary.json`` within ``output_dir``."""

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "summary.json"
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return path


@dataclass(slots=True, frozen=True)
class SmokeE2EConfig:
    """Configuration bundle for the smoke pipeline."""

    csv_path: Path
    output_dir: Path
    seed: int = 20240615
    fee: float = 0.0005
    momentum_window: int = 12


@dataclass(slots=True, frozen=True)
class SmokeE2EArtifacts:
    """Paths to artefacts generated by the pipeline."""

    summary_path: Path
    report_path: Path | None


@dataclass(slots=True, frozen=True)
class SmokeE2ERun:
    """Return payload from :class:`SmokeE2EPipeline`."""

    seed: int
    metrics: Mapping[str, Any]
    ingested_ticks: int
    backtest: Result
    summary: Mapping[str, Any]
    artifacts: SmokeE2EArtifacts


class SmokeE2EPipeline:
    """High-level orchestrator composing the smoke pipeline primitives."""

    def __init__(
        self,
        *,
        analyzer: AnalyzeRunner | None = None,
        ingestor: IngestRunner | None = None,
        signal_builder: SignalBuilder | None = None,
        backtester: BacktestRunner | None = None,
        artifact_writer: ArtifactWriter | None = None,
    ) -> None:
        self._analyzer = analyzer or run_cli_analyze
        self._ingestor = ingestor or ingest_prices
        self._signal_builder = signal_builder or build_signal_function
        self._backtester = backtester or run_backtest
        self._artifact_writer = artifact_writer or write_summary

    def run(self, config: SmokeE2EConfig) -> SmokeE2ERun:
        """Execute the pipeline and persist the summary artefact."""

        csv_path = config.csv_path.resolve()
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV source not found: {csv_path}")

        seed_everything(config.seed)

        metrics = dict(self._analyzer(csv_path, config.seed))
        ticks = list(self._ingestor(csv_path))
        prices = np.array([float(t.price) for t in ticks], dtype=float)
        signal_fn = self._signal_builder(metrics, config.momentum_window)
        result = self._backtester(prices, signal_fn, config.fee)

        summary = dict(summarise_result(result, ticks, metrics))
        summary["seed"] = config.seed

        summary_path = self._artifact_writer(summary, config.output_dir)
        artifacts = SmokeE2EArtifacts(
            summary_path=summary_path,
            report_path=result.report_path,
        )
        return SmokeE2ERun(
            seed=config.seed,
            metrics=metrics,
            ingested_ticks=len(ticks),
            backtest=result,
            summary=summary,
            artifacts=artifacts,
        )


__all__ = [
    "SmokeE2EArtifacts",
    "SmokeE2EConfig",
    "SmokeE2EPipeline",
    "SmokeE2ERun",
    "build_signal_function",
    "ingest_prices",
    "run_cli_analyze",
    "seed_everything",
]
