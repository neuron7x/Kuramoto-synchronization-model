"""Utilities that implement the GitHub Actions orchestrated MLOps pipeline."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from random import Random
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from core.experiments import ArtifactSpec, ModelRegistry

LOGGER = logging.getLogger(__name__)
DEFAULT_ARTIFACT_ROOT = Path("artifacts/mlops")
DEFAULT_REGISTRY_ROOT = Path("artifacts/model-registry")
DEFAULT_EXPERIMENT = "github-actions/nightly-regression"


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
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _derive_seed(config: PipelineConfig) -> int:
    payload = f"{config.commit_sha}:{config.environment}:{config.experiment}".encode()
    digest = sha256(payload).digest()
    return int.from_bytes(digest[:8], "big")


def _normalise(values: np.ndarray) -> np.ndarray:
    mean = float(values.mean())
    std = float(values.std())
    if std == 0.0 or not np.isfinite(std):
        return np.zeros_like(values, dtype=float)
    return (values - mean) / std


def _load_dataset(path: Path | None) -> pd.DataFrame | None:
    if path is None:
        return None
    if not path.exists():
        raise FileNotFoundError(f"Dataset path does not exist: {path}")
    dataset = pd.read_csv(path)
    if dataset.empty:
        raise ValueError(f"Dataset at {path} is empty")
    if "ts" in dataset.columns:
        dataset = dataset.sort_values("ts").reset_index(drop=True)
    return dataset.dropna(axis=0, how="any")


def _generate_synthetic_dataset(seed: int, rows: int = 256) -> pd.DataFrame:
    rng = Random(seed)
    ts = np.arange(rows, dtype=float)
    baseline = 100.0 + 0.05 * ts
    noise = np.array([rng.gauss(0.0, 0.6) for _ in range(rows)], dtype=float)
    price = baseline + noise
    volume = np.array([1000.0 + rng.randint(-60, 60) for _ in range(rows)], dtype=float)
    return pd.DataFrame({"ts": ts, "price": price, "volume": volume})


def _build_design_matrix(dataset: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, list[str]]:
    numeric_columns = [
        column
        for column in dataset.columns
        if np.issubdtype(dataset[column].dtype, np.number)
    ]
    if not numeric_columns:
        raise ValueError("Dataset must contain numeric columns")
    if "price" in dataset.columns and np.issubdtype(dataset["price"].dtype, np.number):
        target_column = "price"
    else:
        target_column = numeric_columns[-1]

    target = dataset[target_column].to_numpy(dtype=float)

    feature_arrays: list[np.ndarray] = []
    feature_names: list[str] = []

    if "ts" in dataset.columns and np.issubdtype(dataset["ts"].dtype, np.number):
        ts_values = dataset["ts"].to_numpy(dtype=float)
    else:
        ts_values = np.arange(dataset.shape[0], dtype=float)
    feature_arrays.append(_normalise(ts_values))
    feature_names.append("ts_normalised")

    if "volume" in dataset.columns and np.issubdtype(dataset["volume"].dtype, np.number):
        feature_arrays.append(_normalise(dataset["volume"].to_numpy(dtype=float)))
        feature_names.append("volume_normalised")

    for column in numeric_columns:
        if column in {target_column, "ts", "volume"}:
            continue
        feature_arrays.append(_normalise(dataset[column].to_numpy(dtype=float)))
        feature_names.append(f"{column}_normalised")

    if not feature_arrays:
        feature_arrays.append(np.zeros(dataset.shape[0], dtype=float))
        feature_names.append("bias_only")

    intercept = np.ones(dataset.shape[0], dtype=float)
    design_matrix = np.column_stack([intercept, *feature_arrays])
    return design_matrix, target, feature_names


def _regression_metrics(target: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    residuals = target - prediction
    mae = float(np.mean(np.abs(residuals)))
    rmse = float(np.sqrt(np.mean(np.square(residuals))))
    if target.size <= 1:
        r2 = 1.0
    else:
        ss_res = float(np.sum(np.square(residuals)))
        ss_tot = float(np.sum(np.square(target - target.mean())))
        if ss_tot == 0.0:
            r2 = 1.0 if ss_res == 0.0 else 0.0
        else:
            r2 = 1.0 - ss_res / ss_tot
    r2 = float(max(-1.0, min(1.0, r2)))
    return {
        "mae": mae,
        "rmse": rmse,
        "r2_score": r2,
    }


def _train_regression_model(
    seed: int, dataset: pd.DataFrame | None
) -> tuple[dict[str, Any], dict[str, float]]:
    dataset_source = "provided" if dataset is not None else "synthetic"
    if dataset is None or dataset.empty:
        dataset = _generate_synthetic_dataset(seed)
        dataset_source = "synthetic"

    try:
        design_matrix, target, feature_names = _build_design_matrix(dataset)
    except ValueError:
        dataset = _generate_synthetic_dataset(seed)
        dataset_source = "synthetic"
        design_matrix, target, feature_names = _build_design_matrix(dataset)

    samples = design_matrix.shape[0]
    if samples < 2:
        dataset = _generate_synthetic_dataset(seed)
        dataset_source = "synthetic"
        design_matrix, target, feature_names = _build_design_matrix(dataset)
        samples = design_matrix.shape[0]

    train_size = int(samples * 0.8)
    train_size = min(max(train_size, 1), samples - 1)
    if samples == 1:
        train_size = 1

    x_train = design_matrix[:train_size]
    y_train = target[:train_size]
    x_valid = design_matrix[train_size:]
    y_valid = target[train_size:]
    validation_source = "holdout" if y_valid.size else "training"

    if y_valid.size == 0:
        x_valid = x_train
        y_valid = y_train

    coefficients, *_ = np.linalg.lstsq(x_train, y_train, rcond=None)
    predictions = x_valid @ coefficients
    metrics = _regression_metrics(y_valid, predictions)

    weights = coefficients[1:]
    mean_abs_weight = float(np.mean(np.abs(weights))) if weights.size else 0.0
    metrics.update(
        {
            "weight_l1_norm": float(np.sum(np.abs(weights))),
            "weight_l2_norm": float(np.linalg.norm(weights)),
            "mean_abs_weight": mean_abs_weight,
            "stability_index": float(1.0 / (1.0 + mean_abs_weight)),
        }
    )

    coefficient_map = {
        name: round(float(value), 8)
        for name, value in zip(feature_names, weights.tolist())
    }

    payload = {
        "intercept": round(float(coefficients[0]), 8),
        "weights": [round(float(value), 8) for value in weights.tolist()],
        "coefficients": coefficient_map,
        "feature_names": feature_names,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "seed": seed,
        "dataset_source": dataset_source,
        "training_rows": int(y_train.size),
        "validation_rows": int(y_valid.size),
        "total_rows": int(target.size),
        "validation_source": validation_source,
    }

    rounded_metrics = {key: round(value, 6) for key, value in metrics.items()}
    return payload, rounded_metrics


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
        ArtifactSpec(model_path, name="model.json", kind="model", metadata={"format": "json"}),
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
    seed: int,
) -> str:
    registry = ModelRegistry(config.registry_root)
    run = registry.register_run(
        config.experiment,
        parameters={
            "seed": seed,
            "environment": config.environment,
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
    dataset = _load_dataset(config.dataset_path)
    payload, metrics = _train_regression_model(seed, dataset)
    LOGGER.info(
        "Trained regression model",
        extra={
            "coefficients": payload.get("coefficients"),
            "dataset_source": payload.get("dataset_source"),
            "metrics": metrics,
        },
    )
    artifacts, summary_path = _persist_artifacts(config, payload, metrics)
    run_id = _register_run(config, artifacts, metrics, seed)
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
        dataset_path=Path(args.dataset_path).expanduser().resolve()
        if getattr(args, "dataset_path", None)
        else None,
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
