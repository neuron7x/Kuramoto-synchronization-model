"""Lightweight logger wrapper for optional MLflow/W&B usage."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


class Logger:
    """Auto-MLflow/W&B if available; else no-op."""

    def __init__(self, params: dict | None = None) -> None:
        self.mlflow = None
        self.wandb = None
        self.run = None
        try:
            import mlflow  # type: ignore

            self.mlflow = mlflow
            uri = os.getenv("MLFLOW_TRACKING_URI", None)
            if uri:
                self.mlflow.set_tracking_uri(uri)
            exp = os.getenv("MLFLOW_EXPERIMENT_NAME", "neurotrade_v12")
            self.mlflow.set_experiment(exp)
            self.run = self.mlflow.start_run()
            if params:
                self.mlflow.log_params(params)
        except Exception as exc:
            logger.info(
                "module=%s mlflow unavailable error=%s",
                __name__,
                exc,
            )
            self.mlflow = None
        try:
            import wandb  # type: ignore

            self.wandb = wandb
            if os.getenv("WANDB_API_KEY", None):
                self.wandb.init(
                    project=os.getenv("WANDB_PROJECT", "neurotrade_v12"),
                    config=params or {},
                )
        except Exception as exc:
            logger.info(
                "module=%s wandb unavailable error=%s",
                __name__,
                exc,
            )
            self.wandb = None

    def log_metric(self, key: str, value: float, step: int | None = None) -> None:
        try:
            if self.mlflow and self.run:
                self.mlflow.log_metric(key, float(value), step=step or 0)
        except Exception as exc:
            logger.warning(
                "module=%s mlflow log_metric failed key=%s value=%s error=%s",
                __name__,
                key,
                value,
                exc,
            )
        try:
            if self.wandb:
                self.wandb.log({key: float(value)})
        except Exception as exc:
            logger.warning(
                "module=%s wandb log_metric failed key=%s value=%s error=%s",
                __name__,
                key,
                value,
                exc,
            )

    def log_artifact(self, path: str) -> None:
        try:
            if self.mlflow and self.run:
                self.mlflow.log_artifact(path)
        except Exception as exc:
            logger.warning(
                "module=%s mlflow log_artifact failed path=%s error=%s",
                __name__,
                path,
                exc,
            )
        try:
            if self.wandb:
                self.wandb.save(path)
        except Exception as exc:
            logger.warning(
                "module=%s wandb save failed path=%s error=%s",
                __name__,
                path,
                exc,
            )

    def end(self) -> None:
        try:
            if self.mlflow and self.run:
                self.mlflow.end_run()
        except Exception as exc:
            logger.warning(
                "module=%s mlflow end_run failed error=%s",
                __name__,
                exc,
            )
        try:
            if self.wandb:
                self.wandb.finish()
        except Exception as exc:
            logger.warning(
                "module=%s wandb finish failed error=%s",
                __name__,
                exc,
            )
