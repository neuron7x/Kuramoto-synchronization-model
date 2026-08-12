# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Lightweight logger wrapper for optional MLflow/W&B usage."""

from __future__ import annotations

import os


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
            exp = os.getenv("MLFLOW_EXPERIMENT_NAME", "geosync_v12")
            self.mlflow.set_experiment(exp)
            self.run = self.mlflow.start_run()
            if params:
                self.mlflow.log_params(params)
        except Exception:
            self.mlflow = None
        try:
            import wandb  # type: ignore

            self.wandb = wandb
            if os.getenv("WANDB_API_KEY", None):
                self.wandb.init(
                    project=os.getenv("WANDB_PROJECT", "geosync_v12"),
                    config=params or {},
                )
        except Exception:
            self.wandb = None

    def log_metric(self, key: str, value: float, step: int | None = None) -> None:
        try:
            if self.mlflow and self.run:
                self.mlflow.log_metric(key, float(value), step=step or 0)
        except Exception:
            pass
        try:
            if self.wandb:
                self.wandb.log({key: float(value)})
        except Exception:
            pass

    def log_artifact(self, path: str) -> None:
        try:
            if self.mlflow and self.run:
                self.mlflow.log_artifact(path)
        except Exception:
            pass
        try:
            if self.wandb:
                self.wandb.save(path)
        except Exception:
            pass

    def end(self) -> None:
        try:
            if self.mlflow and self.run:
                self.mlflow.end_run()
        except Exception:
            pass
        try:
            if self.wandb:
                self.wandb.finish()
        except Exception:
            pass
