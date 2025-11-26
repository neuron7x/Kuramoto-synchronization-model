"""Utilities that implement the GitHub Actions orchestrated MLOps pipeline.

This module previously synthesised pseudo-random model weights to mimic a
training workflow.  The implementation now performs a small but fully
deterministic statistical training step so generated artifacts reflect real
data derived from the supplied dataset (or the repository sample).  Metrics are
calculated from the fitted model and persisted alongside the artifacts to make
the pipeline outputs meaningful for regression testing and auditing.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from core.experiments import ArtifactSpec, ModelRegistry

LOGGER = logging.getLogger(__name__)
DEFAULT_ARTIFACT_ROOT = Path("artifacts/mlops")
DEFAULT_REGISTRY_ROOT = Path("artifacts/model-registry")
DEFAULT_EXPERIMENT = "github-actions/nightly-regression"
DEFAULT_DATASET = Path("sample.csv")
MIN_REQUIRED_POINTS = 64
DEFAULT_LOOKBACK_RANGE = (5, 12)


@dataclass(slots=True)
class PipelineConfig:
    """Configuration parameters driving the orchestrated pipeline."""

    artifact_root: Path
    registry_root: Path
    experiment: str
    commit_sha: str
    environment: str
    dataset_path: Path | None = None

    @property
    def run_name(self) -> str:
        """Return a filesystem-safe identifier for generated assets."""

        experiment_slug = self.experiment.replace("/", "-").replace(" ", "-")
        commit_fragment = (self.commit_sha or "local").strip()[:7] or "local"
        return f"{experiment_slug}-{commit_fragment}".lower()


def _configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )


def _derive_seed(config: PipelineConfig) -> int:
    payload = f"{config.commit_sha}:{config.environment}:{config.experiment}".encode()
    digest = sha256(payload).digest()
    return int.from_bytes(digest[:8], "big")


def _dataset_path(config: PipelineConfig) -> Path:
    if config.dataset_path:
        return config.dataset_path
    # Resolve repository sample dataset relative to this module.
    candidate = (Path(__file__).resolve().parents[2] / DEFAULT_DATASET).resolve()
    if not candidate.exists():
        msg = (
            "Default dataset not found. Provide --dataset-path when invoking the "
            "pipeline."
        )
        raise FileNotFoundError(msg)
    return candidate


def _load_closing_prices(dataset: Path) -> np.ndarray:
    if not dataset.exists():
        raise FileNotFoundError(f"Dataset '{dataset}' does not exist.")

    closes: list[float] = []
    with dataset.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("Dataset must include a header row.")

        candidate_cols = [name for name in reader.fieldnames if name]
        try:
            close_column = next(col for col in candidate_cols if col.lower() == "close")
        except StopIteration as exc:
            raise ValueError("Dataset must contain a 'close' column.") from exc

        for row in reader:
            raw_value = row.get(close_column)
            if raw_value in (None, ""):
                continue
            try:
                closes.append(float(raw_value))
            except ValueError as exc:
                raise ValueError(
                    f"Invalid numeric value {raw_value!r} in column '{close_column}'."
                ) from exc

    prices = np.asarray(closes, dtype=float)
    if prices.size < MIN_REQUIRED_POINTS:
        raise ValueError(
            f"Dataset '{dataset}' must contain at least {MIN_REQUIRED_POINTS} rows; "
            f"found {prices.size}."
        )
    return prices


def _select_lookback(seed: int) -> int:
    lower, upper = DEFAULT_LOOKBACK_RANGE
    span = upper - lower + 1
    if span <= 0:
        return lower
    return lower + (seed % span)


def _prepare_regression(
    prices: np.ndarray, lookback: int
) -> tuple[np.ndarray, np.ndarray]:
    returns = np.diff(prices) / np.maximum(prices[:-1], 1e-9)
    if returns.size <= lookback:
        raise ValueError(
            "Dataset too small for requested lookback window "
            f"(need > {lookback + 1} price points)."
        )

    design = np.lib.stride_tricks.sliding_window_view(returns, lookback)
    targets = returns[lookback:]
    # design currently shape (n_samples, lookback); align with targets length
    if design.shape[0] != targets.shape[0]:
        design = design[: targets.shape[0]]
    return design, targets


def _fit_linear_model(
    features: np.ndarray, targets: np.ndarray
) -> tuple[np.ndarray, float, np.ndarray]:
    ones = np.ones((features.shape[0], 1), dtype=float)
    X = np.concatenate([ones, features], axis=1)
    solution, *_ = np.linalg.lstsq(X, targets, rcond=None)
    intercept = float(solution[0])
    coefficients = solution[1:]
    predictions = X @ solution
    return coefficients, intercept, predictions


def _compute_metrics_from_predictions(
    targets: np.ndarray, predictions: np.ndarray
) -> dict[str, float]:
    residuals = predictions - targets
    mse = float(np.mean(residuals**2))
    mae = float(np.mean(np.abs(residuals)))
    target_var = float(np.var(targets))
    residual_var = float(np.var(residuals))
    r2 = 0.0 if target_var == 0.0 else float(1.0 - residual_var / target_var)
    if targets.size:
        direction = float(np.mean(np.sign(predictions) == np.sign(targets)))
    else:
        direction = 0.0
    return {
        "mean_squared_error": round(mse, 8),
        "mean_absolute_error": round(mae, 8),
        "r_squared": round(r2, 8),
        "directional_accuracy": round(direction, 8),
    }


def _model_payload(
    coefficients: np.ndarray,
    intercept: float,
    lookback: int,
    dataset: Path,
) -> dict[str, Any]:
    generated_at = datetime.now(tz=timezone.utc).isoformat()
    dataset_hash = sha256(dataset.read_bytes()).hexdigest()
    return {
        "model": {
            "type": "linear_regression",
            "intercept": round(intercept, 10),
            "coefficients": [round(float(value), 10) for value in coefficients],
            "lookback": lookback,
        },
        "dataset": {
            "path": str(dataset),
            "sha256": dataset_hash,
        },
        "generated_at": generated_at,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _persist_artifacts(
    config: PipelineConfig,
    payload: dict[str, Any],
    metrics: dict[str, float],
) -> tuple[list[ArtifactSpec], Path]:
    artifact_root = config.artifact_root
    artifact_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=timezone.utc).isoformat()
    model_path = artifact_root / "model" / f"{config.run_name}.json"
    metrics_path = artifact_root / "reports" / "metrics.json"
    context_path = artifact_root / "reports" / "context.json"
    summary_path = artifact_root / "summary.json"

    _write_json(model_path, payload)
    _write_json(metrics_path, {"metrics": metrics, "generated_at": timestamp})
    _write_json(
        context_path,
        {
            "environment": config.environment,
            "experiment": config.experiment,
            "commit": config.commit_sha,
            "dataset": str(config.dataset_path) if config.dataset_path else None,
            "timestamp": timestamp,
        },
    )

    artifacts: list[ArtifactSpec] = [
        ArtifactSpec(
            model_path, name="model.json", kind="model", metadata={"format": "json"}
        ),
        ArtifactSpec(
            metrics_path,
            name="metrics.json",
            kind="metrics",
            metadata={"generated_at": timestamp},
        ),
        ArtifactSpec(context_path, name="context.json", kind="context"),
    ]

    if config.dataset_path and config.dataset_path.exists():
        dataset_target = artifact_root / "datasets" / config.dataset_path.name
        dataset_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(config.dataset_path, dataset_target)
        artifacts.append(
            ArtifactSpec(
                dataset_target,
                name=config.dataset_path.name,
                kind="dataset",
                metadata={"source": str(config.dataset_path)},
            )
        )

    _write_json(
        summary_path,
        {
            "created_at": timestamp,
            "model_path": str(model_path),
            "metrics_path": str(metrics_path),
            "context_path": str(context_path),
        },
    )

    return artifacts, summary_path


def _register_run(
    config: PipelineConfig,
    artifacts: Iterable[ArtifactSpec],
    metrics: dict[str, float],
    model_info: Mapping[str, Any],
    seed: int,
) -> str:
    registry = ModelRegistry(config.registry_root)
    run = registry.register_run(
        config.experiment,
        parameters={
            "seed": seed,
            "environment": config.environment,
            "model": model_info,
        },
        metrics=metrics,
        artifacts=artifacts,
        tags=["github-actions", config.environment],
        notes="Automated training orchestrated by GitHub Actions.",
        metadata={
            "commit": config.commit_sha,
            "dataset": str(config.dataset_path) if config.dataset_path else None,
        },
    )
    return run.id


def orchestrate_pipeline(config: PipelineConfig) -> dict[str, Any]:
    seed = _derive_seed(config)
    LOGGER.info("Derived deterministic seed", extra={"seed": seed})

    dataset = _dataset_path(config)
    prices = _load_closing_prices(dataset)
    lookback = _select_lookback(seed)
    features, targets = _prepare_regression(prices, lookback)
    coefficients, intercept, predictions = _fit_linear_model(features, targets)
    metrics = _compute_metrics_from_predictions(targets, predictions)
    payload = _model_payload(coefficients, intercept, lookback, dataset)

    LOGGER.info(
        "Trained deterministic linear model",
        extra={
            "lookback": lookback,
            "coefficients": payload["model"]["coefficients"],
            "intercept": payload["model"]["intercept"],
        },
    )
    LOGGER.info("Computed evaluation metrics", extra=metrics)
    artifacts, summary_path = _persist_artifacts(config, payload, metrics)
    run_id = _register_run(
        config,
        artifacts,
        metrics,
        model_info=payload["model"],
        seed=seed,
    )
    LOGGER.info("Registered run in local model registry", extra={"run_id": run_id})

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary.update(
        {
            "run_id": run_id,
            "registry_path": str(config.registry_root.resolve()),
            "metrics": metrics,
        }
    )
    _write_json(summary_path, summary)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=DEFAULT_ARTIFACT_ROOT,
        help="Directory where training artifacts will be written.",
    )
    parser.add_argument(
        "--registry-root",
        type=Path,
        default=DEFAULT_REGISTRY_ROOT,
        help="Location of the file-backed model registry.",
    )
    parser.add_argument(
        "--experiment",
        default=DEFAULT_EXPERIMENT,
        help="Experiment name recorded in the registry.",
    )
    parser.add_argument(
        "--commit-sha",
        default=os.environ.get("GITHUB_SHA", "local"),
        help="Commit SHA associated with the training run.",
    )
    parser.add_argument(
        "--environment",
        default=os.environ.get("GITHUB_REF_NAME", "local"),
        help="Logical deployment environment (e.g. staging, production).",
    )
    parser.add_argument(
        "--dataset-path",
        type=Path,
        default=None,
        help="Optional dataset included alongside the generated artifacts.",
    )
    return parser


def _build_config(args: argparse.Namespace) -> PipelineConfig:
    return PipelineConfig(
        artifact_root=Path(args.artifact_root).expanduser().resolve(),
        registry_root=Path(args.registry_root).expanduser().resolve(),
        experiment=str(args.experiment),
        commit_sha=str(args.commit_sha),
        environment=str(args.environment),
        dataset_path=(
            Path(args.dataset_path).expanduser().resolve()
            if getattr(args, "dataset_path", None)
            else None
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    _configure_logging()
    config = _build_config(args)
    summary = orchestrate_pipeline(config)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
