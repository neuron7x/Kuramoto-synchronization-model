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


def _synthesise_model_payload(seed: int) -> dict[str, Any]:
    rng = Random(seed)
    weights = [round(rng.uniform(-1.0, 1.0), 6) for _ in range(6)]
    biases = [round(rng.uniform(-0.5, 0.5), 6) for _ in range(2)]
    generated_at = datetime.now(tz=timezone.utc).isoformat()
    return {
        "weights": weights,
        "biases": biases,
        "generated_at": generated_at,
        "seed": seed,
    }


def _compute_metrics(payload: dict[str, Any]) -> dict[str, float]:
    weights = payload["weights"]
    l1_norm = sum(abs(weight) for weight in weights)
    mean_abs_weight = l1_norm / len(weights)
    stability = 1.0 / (1.0 + mean_abs_weight)
    pseudo_accuracy = max(0.0, min(1.0, 1.0 - mean_abs_weight / 2.0))
    return {
        "mean_abs_weight": round(mean_abs_weight, 6),
        "stability_index": round(stability, 6),
        "pseudo_accuracy": round(pseudo_accuracy, 6),
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
    payload = _synthesise_model_payload(seed)
    LOGGER.info("Synthesised model payload", extra={"weights": payload["weights"]})
    metrics = _compute_metrics(payload)
    LOGGER.info("Computed evaluation metrics", extra=metrics)
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
