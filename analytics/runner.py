# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Hydra-powered experiment runner for TradePulse analytics."""
from __future__ import annotations

import json
import logging
import os
import platform
import random
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import hydra
import numpy as np
import pandas as pd
from hydra.utils import get_original_cwd, to_absolute_path
from omegaconf import DictConfig, OmegaConf

from analytics import _config_sanitizer as _config_sanitizer
from analytics._config_sanitizer import redacted_config_yaml
from analytics.tracking import (
    ExperimentDeviationError,
    ExperimentTracker,
    NullExperimentTracker,
)
from core.config.hydra_profiles import (
    ExperimentProfileError,
    ExperimentProfileRegistry,
    validate_experiment_profile,
)
from core.indicators.entropy import delta_entropy, entropy
from core.indicators.kuramoto import compute_phase, kuramoto_order
from core.indicators.ricci import build_price_graph, mean_ricci

REDACTED_PLACEHOLDER: str = _config_sanitizer._REDACTED_PLACEHOLDER


def _redact_sensitive_data(data: Any) -> Any:
    """Return a copy of ``data`` with sensitive tokens masked."""

    return _config_sanitizer._redact_sensitive_data(data)


def _redacted_config_yaml(cfg: DictConfig) -> str:
    """Serialize ``cfg`` to YAML with sensitive values redacted."""

    return redacted_config_yaml(cfg)


@dataclass(slots=True)
class RunMetadata:
    """Container for metadata captured for reproducibility."""

    run_dir: Path
    original_cwd: Path
    timestamp_utc: str
    git_sha: str | None
    python_version: str
    environment: str
    random_seed: int


def configure_logging(level_name: str) -> None:
    """Configure root logging with the requested level."""

    numeric_level = logging.getLevelName(level_name.upper())
    if isinstance(numeric_level, str):  # logging returns a string when lookup fails
        numeric_level = logging.INFO
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    )


def set_random_seeds(seed: int) -> None:
    """Set deterministic seeds for Python's random and NumPy generators."""

    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed)


def apply_reproducibility_settings(cfg: DictConfig) -> None:
    """Apply optional reproducibility tweaks defined in the configuration."""

    repro_cfg = cfg.get("reproducibility")
    if repro_cfg is None:
        return

    precision = repro_cfg.get("numpy_print_precision")
    if precision is not None:
        np.set_printoptions(precision=int(precision))


def _current_git_sha(cwd: Path) -> str | None:
    """Return the git SHA for the repository if available."""

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            cwd=str(cwd),
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return result.stdout.strip() or None


def collect_run_metadata(
    run_dir: Path, original_cwd: Path, cfg: DictConfig
) -> RunMetadata:
    """Collect metadata that allows reproducing the current experiment run."""

    timestamp = datetime.now(timezone.utc).isoformat()
    git_sha = _current_git_sha(original_cwd)
    environment = str(cfg.experiment.name)
    seed = int(cfg.experiment.random_seed)
    return RunMetadata(
        run_dir=run_dir,
        original_cwd=original_cwd,
        timestamp_utc=timestamp,
        git_sha=git_sha,
        python_version=platform.python_version(),
        environment=environment,
        random_seed=seed,
    )


def _write_metadata(metadata: RunMetadata) -> None:
    """Persist metadata to the Hydra run directory."""

    payload: dict[str, Any] = asdict(metadata)
    payload["run_dir"] = str(metadata.run_dir)
    payload["original_cwd"] = str(metadata.original_cwd)
    metadata_path = metadata.run_dir / "run_metadata.json"
    metadata_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_pipeline(
    cfg: DictConfig, tracker: ExperimentTracker | None = None
) -> dict[str, Any]:
    """Execute the analytics pipeline using configuration parameters."""

    logger = logging.getLogger("tradepulse.experiment")
    tracker = tracker or NullExperimentTracker()
    data_cfg = cfg.experiment.data
    analytics_cfg = cfg.experiment.analytics

    data_path = Path(to_absolute_path(str(data_cfg.price_csv)))
    tracker.log_data_version(data_path)
    if not data_path.exists():
        logger.warning(
            "Data file %s does not exist; analytics step skipped.", data_path
        )
        tracker.record_status("missing-data", {"path": str(data_path)})
        return {"status": "missing-data", "path": str(data_path)}

    df = pd.read_csv(data_path)
    tracker.record_status("data-loaded", {"rows": len(df), "columns": list(df.columns)})
    price_column = str(data_cfg.price_column)
    if price_column not in df.columns:
        tracker.record_status(
            "invalid-data",
            {"price_column": price_column, "available_columns": list(df.columns)},
        )
        raise ValueError(
            f"Price column '{price_column}' not found in dataset columns {list(df.columns)}"
        )

    prices = df[price_column].to_numpy()
    window = int(analytics_cfg.window)
    bins = int(analytics_cfg.bins)
    delta = float(analytics_cfg.delta)

    if len(prices) < window:
        tracker.record_status(
            "insufficient-data",
            {"observations": len(prices), "window": window},
        )
        raise ValueError(
            f"Not enough price observations ({len(prices)}) for window size {window}."
        )

    phases = compute_phase(prices)
    R = float(kuramoto_order(phases[-window:]))
    H = float(entropy(prices[-window:], bins=bins))
    dH = float(delta_entropy(prices, window=window))
    graph = build_price_graph(prices[-window:], delta=delta)
    kappa = float(mean_ricci(graph))

    summary = {
        "order_parameter": R,
        "entropy": H,
        "delta_entropy": dH,
        "mean_ricci": kappa,
        "window": window,
        "bins": bins,
        "delta": delta,
    }
    tracker.log_metrics(summary)
    tracker.record_status("analytics-completed", summary)
    logger.info("Analytics summary computed: %s", summary)

    results_path = Path.cwd() / "results.json"
    results_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    tracker.log_artifact(results_path)
    return {"status": "ok", "summary": summary, "results_path": str(results_path)}


@hydra.main(config_path="../conf", config_name="config", version_base="1.3")
def main(cfg: DictConfig) -> None:
    """Hydra entrypoint that orchestrates experiment execution."""

    registry: ExperimentProfileRegistry
    try:
        experiment = validate_experiment_profile(cfg)
        registry = ExperimentProfileRegistry.discover()
        selected_profile = OmegaConf.select(
            cfg, "hydra.runtime.choices.experiment", default=None
        )
        if selected_profile is not None:
            registry.ensure(str(selected_profile))
    except ExperimentProfileError as exc:
        raise SystemExit(str(exc)) from exc

    configure_logging(experiment.log_level)
    set_random_seeds(experiment.random_seed)
    apply_reproducibility_settings(cfg)

    run_dir = Path.cwd()
    original_cwd = Path(get_original_cwd())
    metadata = collect_run_metadata(run_dir, original_cwd, cfg)

    logger = logging.getLogger(__name__)
    logger.info(
        "Using Hydra experiment profile '%s'. Available profiles: %s",
        experiment.name,
        ", ".join(registry.names()),
    )
    tracker = ExperimentTracker.from_experiment(experiment, metadata)
    safe_yaml: str | None
    try:
        safe_yaml = redacted_config_yaml(cfg)
    except Exception:
        logger.warning(
            "Unable to serialize configuration for safe logging; output suppressed.",
            exc_info=True,
        )
        safe_yaml = None
    if safe_yaml is not None:
        logger.info("Running with configuration:\n%s", safe_yaml)
    tracker.log_configuration(cfg, safe_yaml)

    _write_metadata(metadata)
    tracker.log_metadata(metadata)

    try:
        results = run_pipeline(cfg, tracker=tracker)
    except ExperimentDeviationError as exc:
        tracker.finalize(results=None, error=exc)
        raise SystemExit(str(exc)) from exc
    except Exception as exc:
        tracker.finalize(results=None, error=exc)
        raise
    else:
        results_path = run_dir / "pipeline_results.json"
        results_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
        tracker.log_artifact(results_path)
        tracker.finalize(results=results, error=None)


if __name__ == "__main__":
    main()
